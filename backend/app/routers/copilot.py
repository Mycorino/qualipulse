"""Research Copilot endpoints.

The copilot is the in-context AI assistant. It runs on two surfaces, each
with its own adapter (see ``services/copilot.py`` / ``copilot_interview.py``):

- ``/surveys/{id}/copilot``  — the survey builder
- ``/projects/{id}/copilot`` — the interview-guide builder

``POST .../copilot`` runs one agent turn (proposes changes). The
``.../copilot/conversation`` GET/PUT persist the panel's chat thread so
it resumes when the researcher navigates away and back.
"""

import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from slowapi.util import get_remote_address
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.limiter import limiter
from app.logging_config import logger
from app.models.company import Company
from app.models.project import Project
from app.models.survey import Survey
from app.models.usage import AIUsageLog
from app.schemas.copilot import (
    ConversationState,
    CopilotRequest,
    CopilotResponse,
)
from app.services.copilot import (
    ERROR_REPLY,
    SURVEY_ADAPTER,
    get_conversation,
    get_memory,
    run_copilot_turn,
    run_copilot_turn_stream,
    save_conversation,
)
from app.services.copilot_interview import INTERVIEW_ADAPTER


def _copilot_rate_key(request: Request) -> str:
    """Rate-limit key for copilot turns: the bearer token (per account)
    rather than the IP, so an office NAT isn't collectively throttled and
    one account can't fan out across IPs. Falls back to IP when absent."""
    auth = request.headers.get("authorization")
    if auth:
        return hashlib.sha256(auth.encode()).hexdigest()
    return get_remote_address(request)


def _check_copilot_budget(db: Session, company: Company) -> None:
    """Per-workspace daily spend ceiling. One copilot turn can make up to
    8 Opus calls — without a ceiling, the rate limit alone still permits
    hundreds of dollars a day from a single account."""
    limit = settings.COPILOT_DAILY_COST_LIMIT_USD
    if limit <= 0:
        return
    day_start = datetime.utcnow().replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    spent = (
        db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0))
        .filter(
            AIUsageLog.company_id == company.id,
            AIUsageLog.operation == "copilot",
            AIUsageLog.created_at >= day_start,
        )
        .scalar()
        or 0.0
    )
    if spent >= limit:
        logger.warning(
            "Copilot daily budget reached (company=%s spent=$%.2f limit=$%.2f)",
            company.id, spent, limit,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="copilot_daily_limit_reached",
        )


def _sse_event(event: dict) -> str:
    """Frame one event for an SSE stream. One JSON object per `data:` line."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# Buffering must be off through every proxy or the stream batches at the
# end and defeats the point. nginx in the frontend container respects
# X-Accel-Buffering; Cloud Run streams HTTP/1.1 natively.
_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def _stream_copilot_response(
    engine,
    company_id: str,
    instrument_kind: str,  # "project" | "survey"
    instrument_id: str,
    adapter,
    body: CopilotRequest,
) -> StreamingResponse:
    """Shared streaming response for every copilot surface.

    The generator opens its OWN Session bound to the request's engine —
    Depends(get_db) closes its session as soon as the route returns the
    StreamingResponse, but the body iterator runs after that. Binding to
    ``engine`` (captured from the request session, ``db.get_bind()``) means
    the test conftest's in-memory engine and the production engine both
    work without touching ``SessionLocal`` directly.
    """
    def stream():
        from sqlalchemy.orm import Session as _Session

        from app.models.company import Company as _Company
        from app.models.project import Project as _Project
        from app.models.survey import Survey as _Survey

        # The turn engine guarantees its own terminal `done` event, but the
        # wrapper here can still fail (instrument deleted between the
        # ownership check and iteration start, engine errors, serialization).
        # Without a catch, Starlette aborts the response mid-stream and the
        # client hangs until its idle timeout — so ALWAYS emit a terminal
        # event. GeneratorExit (client disconnect) must propagate untouched.
        lang = "en"
        try:
            with _Session(engine) as gen_db:
                comp = gen_db.query(_Company).filter(
                    _Company.id == company_id
                ).one()
                if (comp.preferred_language or "en").startswith("fr"):
                    lang = "fr"
                if instrument_kind == "project":
                    inst = gen_db.query(_Project).filter(
                        _Project.id == instrument_id
                    ).one()
                elif instrument_kind == "survey":
                    inst = gen_db.query(_Survey).filter(
                        _Survey.id == instrument_id
                    ).one()
                else:
                    raise ValueError(
                        f"Unknown instrument kind: {instrument_kind}"
                    )
                for event in run_copilot_turn_stream(
                    gen_db, comp, inst, adapter, body.messages,
                    body.active_section, body.mission,
                ):
                    yield _sse_event(event)
        except GeneratorExit:
            raise
        except Exception as exc:
            logger.error(
                "Copilot stream wrapper failed (%s %s): %s",
                instrument_kind, instrument_id, exc,
            )
            yield _sse_event(
                {
                    "type": "done",
                    "reply": ERROR_REPLY[lang],
                    "proposed_actions": [],
                    "memory_updated": False,
                    "error": True,
                }
            )

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers=_SSE_HEADERS,
    )

router = APIRouter(tags=["copilot"])


def _survey_or_404(db: Session, survey_id: str, company: Company) -> Survey:
    survey = (
        db.query(Survey)
        .filter(Survey.id == survey_id, Survey.company_id == company.id)
        .first()
    )
    if survey is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Survey not found"
        )
    return survey


def _project_or_404(db: Session, project_id: str, company: Company) -> Project:
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.company_id == company.id)
        .first()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    return project


# ── Survey surface ───────────────────────────────────────────────────────────


@router.post("/surveys/{survey_id}/copilot")
@limiter.limit(settings.RATE_LIMIT_COPILOT, key_func=_copilot_rate_key)
def survey_copilot(
    request: Request,
    survey_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StreamingResponse:
    """Run one Research Copilot turn against a survey — SSE stream.
    See project_copilot for the event schema and the session-lifetime
    workaround for Depends(get_db) under StreamingResponse."""
    _survey_or_404(db, survey_id, company)
    _check_copilot_budget(db, company)
    return _stream_copilot_response(
        engine=db.get_bind(),
        company_id=company.id,
        instrument_kind="survey",
        instrument_id=survey_id,
        adapter=SURVEY_ADAPTER,
        body=body,
    )


@router.get(
    "/surveys/{survey_id}/copilot/conversation", response_model=ConversationState
)
def get_survey_conversation(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _survey_or_404(db, survey_id, company)
    thread, version = get_conversation(db, "survey", survey_id)
    return ConversationState(thread=thread, version=version)


@router.put(
    "/surveys/{survey_id}/copilot/conversation", response_model=ConversationState
)
def put_survey_conversation(
    survey_id: str,
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _survey_or_404(db, survey_id, company)
    new_version = save_conversation(
        db, company.id, "survey", survey_id, body.thread, body.version,
    )
    return ConversationState(thread=body.thread, version=new_version)


# ── Interview-guide surface ──────────────────────────────────────────────────


@router.post("/projects/{project_id}/copilot")
@limiter.limit(settings.RATE_LIMIT_COPILOT, key_func=_copilot_rate_key)
def project_copilot(
    request: Request,
    project_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StreamingResponse:
    """Run one Research Copilot turn against an interview guide — streams
    progress + the reply text as SSE. The terminal `done` event carries
    the authoritative {reply, proposed_actions, memory_updated}."""
    _project_or_404(db, project_id, company)
    _check_copilot_budget(db, company)
    return _stream_copilot_response(
        engine=db.get_bind(),
        company_id=company.id,
        instrument_kind="project",
        instrument_id=project_id,
        adapter=INTERVIEW_ADAPTER,
        body=body,
    )


@router.get(
    "/projects/{project_id}/copilot/conversation", response_model=ConversationState
)
def get_project_conversation(
    project_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _project_or_404(db, project_id, company)
    thread, version = get_conversation(db, "project", project_id)
    return ConversationState(thread=thread, version=version)


@router.put(
    "/projects/{project_id}/copilot/conversation", response_model=ConversationState
)
def put_project_conversation(
    project_id: str,
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    _project_or_404(db, project_id, company)
    new_version = save_conversation(
        db, company.id, "project", project_id, body.thread, body.version,
    )
    return ConversationState(thread=body.thread, version=new_version)
