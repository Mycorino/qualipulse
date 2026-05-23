"""Research Copilot endpoints.

The copilot is the in-context AI assistant. It runs on two surfaces, each
with its own adapter (see ``services/copilot.py`` / ``copilot_interview.py``):

- ``/surveys/{id}/copilot``  — the survey builder
- ``/projects/{id}/copilot`` — the interview-guide builder

``POST .../copilot`` runs one agent turn (proposes changes). The
``.../copilot/conversation`` GET/PUT persist the panel's chat thread so
it resumes when the researcher navigates away and back.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.project import Project
from app.models.survey import Survey
from app.schemas.copilot import ConversationState, CopilotRequest, CopilotResponse
from app.services.copilot import (
    SURVEY_ADAPTER,
    get_conversation,
    get_memory,
    run_copilot_turn,
    run_copilot_turn_stream,
    save_conversation,
)
from app.services.copilot_interview import INTERVIEW_ADAPTER
from app.services.copilot_onboarding import ONBOARDING_ADAPTER


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
    instrument_kind: str,  # "project" | "survey" | "company"
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

        with _Session(engine) as gen_db:
            comp = gen_db.query(_Company).filter(_Company.id == company_id).one()
            if instrument_kind == "company":
                inst = comp
            elif instrument_kind == "project":
                inst = gen_db.query(_Project).filter(
                    _Project.id == instrument_id
                ).one()
            elif instrument_kind == "survey":
                inst = gen_db.query(_Survey).filter(
                    _Survey.id == instrument_id
                ).one()
            else:
                raise ValueError(f"Unknown instrument kind: {instrument_kind}")
            for event in run_copilot_turn_stream(
                gen_db, comp, inst, adapter, body.messages,
                body.active_section, body.mission,
            ):
                yield _sse_event(event)

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
def survey_copilot(
    survey_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StreamingResponse:
    """Run one Research Copilot turn against a survey — SSE stream.
    See project_copilot for the event schema and the session-lifetime
    workaround for Depends(get_db) under StreamingResponse."""
    _survey_or_404(db, survey_id, company)
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
    return ConversationState(thread=get_conversation(db, "survey", survey_id))


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
    save_conversation(db, company.id, "survey", survey_id, body.thread)
    return body


# ── Interview-guide surface ──────────────────────────────────────────────────


@router.post("/projects/{project_id}/copilot")
def project_copilot(
    project_id: str,
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StreamingResponse:
    """Run one Research Copilot turn against an interview guide — streams
    progress + the reply text as SSE. The terminal `done` event carries
    the authoritative {reply, proposed_actions, memory_updated}."""
    _project_or_404(db, project_id, company)
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
    return ConversationState(thread=get_conversation(db, "project", project_id))


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
    save_conversation(db, company.id, "project", project_id, body.thread)
    return body


# ── Onboarding surface ───────────────────────────────────────────────────────


@router.post("/onboarding/copilot")
def onboarding_copilot(
    body: CopilotRequest,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> StreamingResponse:
    """Run one onboarding-copilot turn — the new researcher's first
    conversation. The 'instrument' is the Company itself. SSE stream."""
    return _stream_copilot_response(
        engine=db.get_bind(),
        company_id=company.id,
        instrument_kind="company",
        instrument_id=company.id,
        adapter=ONBOARDING_ADAPTER,
        body=body,
    )


@router.get("/onboarding/copilot/conversation", response_model=ConversationState)
def get_onboarding_conversation(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    return ConversationState(
        thread=get_conversation(db, "company", company.id),
    )


@router.put("/onboarding/copilot/conversation", response_model=ConversationState)
def put_onboarding_conversation(
    body: ConversationState,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> ConversationState:
    save_conversation(db, company.id, "company", company.id, body.thread)
    return body


@router.get("/onboarding/copilot/memory")
def get_onboarding_memory(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> dict:
    """The workspace-scope memory the copilot wrote during onboarding —
    shown back to the researcher on the completion screen.

    Returns both the free-form memory the agent saved AND a deterministic
    ``profile_summary`` built from the captured Company fields plus the
    most recent non-demo Project's strategic context (decision /
    timeline / audience / success criteria). That mix is what makes the
    recap feel earned ("you're a PM at a 50-person SaaS company; your
    decision is in 2 weeks") instead of a generic placeholder.
    """
    row = get_memory(db, "company", company.id)
    # Most recent non-demo Project — created by acceptStudy moments
    # before the completion screen renders.
    from app.models.project import Project

    latest_project = (
        db.query(Project)
        .filter(Project.company_id == company.id, Project.is_demo.is_(False))
        .order_by(Project.created_at.desc())
        .first()
    )
    return {
        "memory": (row.content if row and row.content else ""),
        "profile_summary": _build_profile_summary(company, latest_project),
    }


def _build_profile_summary(
    company: Company, project=None
) -> str:
    """Stitch captured Company fields + Project strategic context into
    a single conversational recap. Returns empty string when there's
    nothing to say (so the frontend can fall back gracefully)."""
    role = (company.role or "").strip()
    size = (company.company_size or "").strip()
    industry = (company.industry or "").strip()
    use_case = (company.use_case or "").strip()
    business = (company.business_summary or "").strip()

    # Who they are: "a Product Manager at a 50-person SaaS company"
    parts: list[str] = []
    if role:
        parts.append(f"You're a {role}")
    if size or industry:
        size_phrase = f"{size}-person " if size else ""
        industry_phrase = industry if industry else "team"
        joiner = " at a " if parts else "You work at a "
        parts.append(f"{joiner}{size_phrase}{industry_phrase} company")

    who = "".join(parts).strip()
    sentences: list[str] = []
    if who:
        sentences.append(who + ".")
    if use_case:
        sentences.append(f"You're using QualiPulse for {use_case.lower()}.")

    # V2 strategic context — pulled from the most recent Project so the
    # recap names the DECISION + TIMELINE, not just the demographic.
    if project is not None:
        decision = (getattr(project, "decision_to_inform", "") or "").strip()
        timeline = (getattr(project, "timeline", "") or "").strip()
        success = (getattr(project, "success_criteria", "") or "").strip()
        if decision:
            sentences.append(f"Decision riding on it: {decision}")
            if timeline:
                sentences[-1] = sentences[-1].rstrip(".") + f" ({timeline})."
            elif not sentences[-1].endswith("."):
                sentences[-1] += "."
        if success:
            sentences.append(f"Success looks like: {success}")
            if not sentences[-1].endswith("."):
                sentences[-1] += "."

    if business:
        snippet = (
            business if len(business) <= 240 else business[:240].rstrip() + "…"
        )
        sentences.append(snippet)

    return " ".join(sentences).strip()
