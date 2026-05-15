"""Surveys router — Sprint 6 minimal API.

CRUD for surveys + survey questions, plus the PUBLIC response collection
endpoint. The public endpoint is the primary thing this sprint ships —
without it the rest of the wedge (Sprints 7+) can't be built or tested.

Auth model:
  - All editor routes use `get_current_company` (workspace-scoped).
  - The public response endpoint takes a link token, no auth.

Token generation reuses the Base58 pattern from links.py to stay consistent.
App-level collision check spans BOTH `interview_links.token` and
`survey_links.token` (see roadmap risk #2).
"""

import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.models.interview import InterviewLink
from app.models.study import ConsentAcknowledgment, Study, StudyParticipant
from app.models.survey import (
    QUESTION_TYPES,
    Survey,
    SurveyLink,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.schemas.survey import (
    AnswerSubmission,
    PublicQuestion,
    PublicSurvey,
    QuestionCreate,
    QuestionPatch,
    QuestionResponse,
    ResponseAck,
    ResponseSubmission,
    SurveyCreate,
    SurveyDashboardSchema,
    SurveyLinkCreate,
    SurveyLinkResponse,
    SurveyPatch,
    SurveyResponse as SurveyResponseSchema,
    QuestionAnalyticsSchema,
    validate_question_config,
)
from app.services.survey_analytics import build_dashboard

router = APIRouter(prefix="/surveys", tags=["surveys"])

# Mirrors links.py to keep token shape consistent across instruments.
_BASE58 = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"


def _generate_link_token(db: Session, length: int = 43) -> str:
    """Generate a token guaranteed to be unique across both link tables.

    Probability of collision in 43 chars of Base58 is negligible per insert,
    but a defensive check here prevents silent corruption if someone reduces
    the length later. Loop bound = 5; if we hit it we raise.
    """

    for _ in range(5):
        token = "".join(secrets.choice(_BASE58) for _ in range(length))
        clash = (
            db.query(InterviewLink.id).filter(InterviewLink.token == token).first()
            or db.query(SurveyLink.id).filter(SurveyLink.token == token).first()
        )
        if not clash:
            return token
    raise HTTPException(status_code=500, detail="Could not generate unique link token")


def _get_or_create_implicit_study(
    db: Session, company: Company, name: str | None = None
) -> Study:
    """Decision 8: Studies are auto-created on first instrument creation.

    A researcher creating their first Survey doesn't see a "create a Study
    first" flow. We create one with the same name as a sensible default.
    """

    study = Study(company_id=company.id, name=name or "Untitled study")
    db.add(study)
    db.flush()
    return study


def _get_survey_or_404(db: Session, survey_id: str, company: Company) -> Survey:
    survey = (
        db.query(Survey)
        .filter(Survey.id == survey_id, Survey.company_id == company.id)
        .first()
    )
    if not survey:
        raise HTTPException(status_code=404, detail="Survey not found")
    return survey


def _survey_to_response(db: Session, survey: Survey) -> SurveyResponseSchema:
    question_count = (
        db.query(func.count(SurveyQuestion.id))
        .filter(
            SurveyQuestion.survey_id == survey.id,
            SurveyQuestion.deprecated_at.is_(None),
        )
        .scalar()
        or 0
    )
    response_count = (
        db.query(func.count(SurveyResponse.id))
        .filter(SurveyResponse.survey_id == survey.id)
        .scalar()
        or 0
    )
    completed_count = (
        db.query(func.count(SurveyResponse.id))
        .filter(
            SurveyResponse.survey_id == survey.id,
            SurveyResponse.completed_at.isnot(None),
        )
        .scalar()
        or 0
    )
    return SurveyResponseSchema(
        id=survey.id,
        study_id=survey.study_id,
        company_id=survey.company_id,
        name=survey.name,
        description=survey.description,
        role=survey.role,  # type: ignore[arg-type]
        status=survey.status,  # type: ignore[arg-type]
        fielding_started_at=survey.fielding_started_at,
        fielding_ended_at=survey.fielding_ended_at,
        created_at=survey.created_at,
        archived_at=survey.archived_at,
        question_count=question_count,
        response_count=response_count,
        completed_count=completed_count,
    )


# ── Survey CRUD ───────────────────────────────────────────────────────


@router.post("/", response_model=SurveyResponseSchema, status_code=status.HTTP_201_CREATED)
def create_survey(
    body: SurveyCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> SurveyResponseSchema:
    if body.study_id:
        study = (
            db.query(Study)
            .filter(Study.id == body.study_id, Study.company_id == company.id)
            .first()
        )
        if not study:
            raise HTTPException(status_code=404, detail="Study not found")
    else:
        study = _get_or_create_implicit_study(db, company, name=body.name)

    survey = Survey(
        study_id=study.id,
        company_id=company.id,
        name=body.name,
        description=body.description,
        role=body.role,
    )
    db.add(survey)
    db.commit()
    db.refresh(survey)
    return _survey_to_response(db, survey)


@router.get("/", response_model=list[SurveyResponseSchema])
def list_surveys(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[SurveyResponseSchema]:
    surveys = (
        db.query(Survey)
        .filter(Survey.company_id == company.id, Survey.archived_at.is_(None))
        .order_by(Survey.created_at.desc())
        .all()
    )
    return [_survey_to_response(db, s) for s in surveys]


@router.get("/{survey_id}", response_model=SurveyResponseSchema)
def get_survey(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> SurveyResponseSchema:
    survey = _get_survey_or_404(db, survey_id, company)
    return _survey_to_response(db, survey)


@router.patch("/{survey_id}", response_model=SurveyResponseSchema)
def patch_survey(
    survey_id: str,
    body: SurveyPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> SurveyResponseSchema:
    survey = _get_survey_or_404(db, survey_id, company)
    if body.name is not None:
        survey.name = body.name
    if body.description is not None:
        survey.description = body.description
    if body.role is not None:
        survey.role = body.role
    if body.status is not None:
        survey.status = body.status
        # When a survey transitions to live for the first time, mark fielding start.
        if body.status == "live" and survey.fielding_started_at is None:
            survey.fielding_started_at = datetime.now(timezone.utc)
        if body.status == "closed" and survey.fielding_ended_at is None:
            survey.fielding_ended_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(survey)
    return _survey_to_response(db, survey)


@router.delete("/{survey_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_survey(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Soft-delete via `archived_at`. Hard delete is reserved for admin tooling."""

    survey = _get_survey_or_404(db, survey_id, company)
    survey.archived_at = datetime.now(timezone.utc)
    db.commit()


# ── Question CRUD ─────────────────────────────────────────────────────


@router.get("/{survey_id}/questions", response_model=list[QuestionResponse])
def list_questions(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[QuestionResponse]:
    _get_survey_or_404(db, survey_id, company)
    questions = (
        db.query(SurveyQuestion)
        .filter(
            SurveyQuestion.survey_id == survey_id,
            SurveyQuestion.deprecated_at.is_(None),
        )
        .order_by(SurveyQuestion.sort_order)
        .all()
    )
    return [
        QuestionResponse(
            id=q.id,
            survey_id=q.survey_id,
            sort_order=q.sort_order,
            type=q.type,  # type: ignore[arg-type]
            prompt=q.prompt,
            is_required=q.is_required,
            config=q.config_dict,
            created_at=q.created_at,
            deprecated_at=q.deprecated_at,
        )
        for q in questions
    ]


@router.post(
    "/{survey_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_question(
    survey_id: str,
    body: QuestionCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> QuestionResponse:
    survey = _get_survey_or_404(db, survey_id, company)
    if body.type not in QUESTION_TYPES:
        raise HTTPException(status_code=422, detail=f"Unknown question type: {body.type}")

    # Auto-append to the end if no explicit sort_order.
    if body.sort_order == 0:
        max_sort = (
            db.query(func.max(SurveyQuestion.sort_order))
            .filter(SurveyQuestion.survey_id == survey.id)
            .scalar()
            or 0
        )
        sort_order = max_sort + 10
    else:
        sort_order = body.sort_order

    question = SurveyQuestion(
        survey_id=survey.id,
        sort_order=sort_order,
        type=body.type,
        prompt=body.prompt,
        is_required=body.is_required,
        config=json.dumps(body.config),
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return QuestionResponse(
        id=question.id,
        survey_id=question.survey_id,
        sort_order=question.sort_order,
        type=question.type,  # type: ignore[arg-type]
        prompt=question.prompt,
        is_required=question.is_required,
        config=question.config_dict,
        created_at=question.created_at,
        deprecated_at=question.deprecated_at,
    )


@router.patch("/{survey_id}/questions/{question_id}", response_model=QuestionResponse)
def patch_question(
    survey_id: str,
    question_id: str,
    body: QuestionPatch,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> QuestionResponse:
    survey = _get_survey_or_404(db, survey_id, company)
    question = (
        db.query(SurveyQuestion)
        .filter(
            SurveyQuestion.id == question_id,
            SurveyQuestion.survey_id == survey.id,
        )
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if body.prompt is not None:
        question.prompt = body.prompt
    if body.is_required is not None:
        question.is_required = body.is_required
    if body.sort_order is not None:
        question.sort_order = body.sort_order
    if body.config is not None:
        # Re-validate against the question's existing type.
        validated = validate_question_config(question.type, body.config)
        question.config = json.dumps(validated)
    db.commit()
    db.refresh(question)
    return QuestionResponse(
        id=question.id,
        survey_id=question.survey_id,
        sort_order=question.sort_order,
        type=question.type,  # type: ignore[arg-type]
        prompt=question.prompt,
        is_required=question.is_required,
        config=question.config_dict,
        created_at=question.created_at,
        deprecated_at=question.deprecated_at,
    )


@router.delete(
    "/{survey_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT
)
def deprecate_question(
    survey_id: str,
    question_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
):
    """Soft delete via `deprecated_at`. Never hard-delete questions with answers."""

    survey = _get_survey_or_404(db, survey_id, company)
    question = (
        db.query(SurveyQuestion)
        .filter(
            SurveyQuestion.id == question_id,
            SurveyQuestion.survey_id == survey.id,
        )
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    question.deprecated_at = datetime.now(timezone.utc)
    db.commit()


# ── Survey Links ──────────────────────────────────────────────────────


@router.post(
    "/{survey_id}/links",
    response_model=SurveyLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_link(
    survey_id: str,
    body: SurveyLinkCreate,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> SurveyLinkResponse:
    survey = _get_survey_or_404(db, survey_id, company)
    token = _generate_link_token(db)
    link = SurveyLink(
        survey_id=survey.id,
        token=token,
        is_anonymous=body.is_anonymous,
        target_n=body.target_n,
        response_cap=body.response_cap,
        opens_at=body.opens_at,
        closes_at=body.closes_at,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return SurveyLinkResponse.model_validate(link)


@router.get("/{survey_id}/links", response_model=list[SurveyLinkResponse])
def list_links(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> list[SurveyLinkResponse]:
    survey = _get_survey_or_404(db, survey_id, company)
    links = db.query(SurveyLink).filter(SurveyLink.survey_id == survey.id).all()
    return [SurveyLinkResponse.model_validate(link) for link in links]


# ── Dashboard (workspace-scoped) ──────────────────────────────────────


@router.get("/{survey_id}/dashboard", response_model=SurveyDashboardSchema)
def get_dashboard(
    survey_id: str,
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> SurveyDashboardSchema:
    """Per-question analytics for the researcher dashboard view.

    Returns Wilson-CI proportions for likert/nps/MC questions; sampled raw
    texts for open-text. Below-min-N segments return `percentage=None` so
    the frontend has no path to render forbidden percentages.
    """

    survey = _get_survey_or_404(db, survey_id, company)
    payload = build_dashboard(db, survey)
    return SurveyDashboardSchema(
        survey_id=payload.survey_id,
        name=payload.name,
        role=payload.role,  # type: ignore[arg-type]
        status=payload.status,  # type: ignore[arg-type]
        fielding_started_at=payload.fielding_started_at,
        fielding_ended_at=payload.fielding_ended_at,
        n_started=payload.n_started,
        n_completed=payload.n_completed,
        completion_rate_percentage=payload.completion_rate_percentage,
        min_n_threshold=payload.min_n_threshold,
        questions=[
            QuestionAnalyticsSchema(
                question_id=q.question_id,
                type=q.type,  # type: ignore[arg-type]
                prompt=q.prompt,
                is_required=q.is_required,
                sort_order=q.sort_order,
                n_answered=q.n_answered,
                min_n_threshold=q.min_n_threshold,
                breakdown=q.breakdown,
                mean=q.mean,
                takeaway=q.takeaway,
            )
            for q in payload.questions
        ],
    )


# ── Public response collection ────────────────────────────────────────


def _resolve_study_participant(
    db: Session,
    study: Study,
    *,
    magic_token: str | None,
    email: str | None,
    display_name: str | None,
    is_anonymous: bool,
) -> StudyParticipant | None:
    """Section 1.3 resolution order: magic token → email → new (or None for anonymous)."""

    if is_anonymous:
        return None

    # 1. Magic token
    if magic_token:
        participant = (
            db.query(StudyParticipant)
            .filter(
                StudyParticipant.study_id == study.id,
                StudyParticipant.magic_token == magic_token,
            )
            .first()
        )
        if participant:
            return participant

    # 2. Email match within the same Study
    email_normalized = _normalize_email(email) if email else None
    if email_normalized:
        existing = (
            db.query(StudyParticipant)
            .filter(
                StudyParticipant.study_id == study.id,
                StudyParticipant.email_normalized == email_normalized,
            )
            .first()
        )
        if existing:
            return existing

        # Cross-study email match — Decision 6 requires consent ack before
        # we link historical records. For now, create fresh in this Study;
        # the consent UX in Sprint 7+ will populate ConsentAcknowledgment.
        # (This branch exists so the resolution is intentional, not silent.)

    # 3. Create new
    participant = StudyParticipant(
        study_id=study.id,
        email_normalized=email_normalized,
        display_name=display_name,
        magic_token=magic_token,
    )
    db.add(participant)
    db.flush()
    return participant


def _normalize_email(email: str) -> str:
    """Lowercase + strip + plus-tag-stripped for join-key purposes only.

    Original email is not stored on StudyParticipant — only the normalized
    join key. This is conservative privacy hygiene.
    """

    cleaned = email.strip().lower()
    if "@" in cleaned:
        local, _, domain = cleaned.partition("@")
        local = local.split("+", 1)[0]
        cleaned = f"{local}@{domain}"
    return cleaned


def _validate_answer_for_type(answer: AnswerSubmission, question: SurveyQuestion) -> None:
    """Per-type validation. Routers don't trust the client."""

    config = question.config_dict
    if question.type in ("likert", "nps"):
        if answer.value_numeric is None:
            raise HTTPException(status_code=422, detail=f"Q {question.id}: numeric value required")
        if question.type == "likert":
            scale = int(config.get("scale", 5))
            if not (1 <= answer.value_numeric <= scale):
                raise HTTPException(
                    status_code=422,
                    detail=f"Q {question.id}: Likert value out of range 1..{scale}",
                )
        if question.type == "nps":
            if not (0 <= answer.value_numeric <= 10):
                raise HTTPException(
                    status_code=422, detail=f"Q {question.id}: NPS value out of range 0..10"
                )
    elif question.type == "mc_single":
        if not answer.value_choice_ids or len(answer.value_choice_ids) != 1:
            raise HTTPException(
                status_code=422, detail=f"Q {question.id}: exactly one choice required"
            )
        valid_ids = {c.get("id") for c in config.get("choices", []) if isinstance(c, dict)}
        if not all(cid in valid_ids for cid in answer.value_choice_ids):
            raise HTTPException(
                status_code=422, detail=f"Q {question.id}: invalid choice id"
            )
    elif question.type == "mc_multi":
        if not answer.value_choice_ids:
            raise HTTPException(
                status_code=422, detail=f"Q {question.id}: at least one choice required"
            )
        max_selectable = config.get("max_selectable")
        if max_selectable and len(answer.value_choice_ids) > max_selectable:
            raise HTTPException(
                status_code=422,
                detail=f"Q {question.id}: max {max_selectable} choices",
            )
        valid_ids = {c.get("id") for c in config.get("choices", []) if isinstance(c, dict)}
        if not all(cid in valid_ids for cid in answer.value_choice_ids):
            raise HTTPException(
                status_code=422, detail=f"Q {question.id}: invalid choice id"
            )
    elif question.type in ("open_text", "short_text"):
        if not answer.value_text:
            if question.is_required:
                raise HTTPException(
                    status_code=422, detail=f"Q {question.id}: text required"
                )
            return
        max_chars = int(config.get("max_chars", 500))
        if len(answer.value_text) > max_chars:
            raise HTTPException(
                status_code=422,
                detail=f"Q {question.id}: text exceeds {max_chars} chars",
            )


@router.post(
    "/{survey_id}/responses",
    response_model=ResponseAck,
    status_code=status.HTTP_201_CREATED,
)
def submit_response(
    survey_id: str,
    body: ResponseSubmission,
    db: Session = Depends(get_db),
):
    """Public endpoint — no auth. Validates the link token, builds the
    response + answer rows, resolves the StudyParticipant, returns an ack."""

    # Resolve link → survey. Constant-time-ish: we always emit "Survey not
    # available" for any failure mode (closed, capped, inactive, missing).
    link = (
        db.query(SurveyLink)
        .filter(SurveyLink.token == body.link_token, SurveyLink.survey_id == survey_id)
        .first()
    )
    if not link or not link.is_active:
        raise HTTPException(status_code=404, detail="Survey not available")

    now = datetime.now(timezone.utc)
    if link.opens_at and now < link.opens_at:
        raise HTTPException(status_code=404, detail="Survey not available")
    if link.closes_at and now > link.closes_at:
        raise HTTPException(status_code=404, detail="Survey not available")

    if link.response_cap is not None:
        current = (
            db.query(func.count(SurveyResponse.id))
            .filter(SurveyResponse.link_id == link.id)
            .scalar()
            or 0
        )
        if current >= link.response_cap:
            raise HTTPException(status_code=404, detail="Survey not available")

    survey = (
        db.query(Survey).filter(Survey.id == link.survey_id).first()
    )
    if not survey or survey.status != "live":
        raise HTTPException(status_code=404, detail="Survey not available")

    study = db.query(Study).filter(Study.id == survey.study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Survey not available")

    # Resolve participant — None when the link is anonymous.
    participant = _resolve_study_participant(
        db,
        study,
        magic_token=body.magic_token,
        email=body.email,
        display_name=body.display_name,
        is_anonymous=link.is_anonymous,
    )

    # Per-type answer validation (server-side; never trust the client).
    questions_by_id = {
        q.id: q
        for q in db.query(SurveyQuestion)
        .filter(
            SurveyQuestion.survey_id == survey.id,
            SurveyQuestion.deprecated_at.is_(None),
        )
        .all()
    }
    for ans in body.answers:
        question = questions_by_id.get(ans.question_id)
        if not question:
            raise HTTPException(
                status_code=422, detail=f"Unknown question id: {ans.question_id}"
            )
        _validate_answer_for_type(ans, question)

    # Required-question check on completed submissions.
    if body.is_complete:
        answered_ids = {a.question_id for a in body.answers}
        for q in questions_by_id.values():
            if q.is_required and q.id not in answered_ids:
                raise HTTPException(
                    status_code=422, detail=f"Required question missing: {q.id}"
                )

    response = SurveyResponse(
        survey_id=survey.id,
        company_id=survey.company_id,
        study_participant_id=participant.id if participant else None,
        link_id=link.id,
        completed_at=now if body.is_complete else None,
        submission_metadata=json.dumps(body.submission_metadata) if body.submission_metadata else None,
    )
    db.add(response)
    db.flush()

    for ans in body.answers:
        db.add(
            SurveyResponseAnswer(
                response_id=response.id,
                question_id=ans.question_id,
                value_numeric=ans.value_numeric,
                value_text=ans.value_text,
                value_choice_ids=json.dumps(ans.value_choice_ids) if ans.value_choice_ids else None,
                time_to_answer_ms=ans.time_to_answer_ms,
            )
        )

    # Auto-set fielding_started_at on first completed response.
    if body.is_complete and survey.fielding_started_at is None:
        survey.fielding_started_at = now

    db.commit()
    db.refresh(response)

    return ResponseAck(
        response_id=response.id,
        study_participant_id=response.study_participant_id,
        is_complete=response.completed_at is not None,
        received_at=response.started_at,
    )
