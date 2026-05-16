"""Public response surface — `/r/{token}` endpoints.

All routes here are anonymous. The respondent flow is:
  1. GET /r/{token} → renders the survey
  2. POST /r/{token}/responses → submits answers

Constant-time-ish "Survey not available" on every unhappy path
(inactive, draft, closed, capped). Same shape as /i/{token} for
interview links — see roadmap risk #9.

The POST endpoint shares its core write logic with the workspace-scoped
POST /surveys/{id}/responses; we route both through the same helpers to
keep validation in one place.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.study import Study
from app.models.survey import (
    Survey,
    SurveyLink,
    SurveyQuestion,
    SurveyResponse,
    SurveyResponseAnswer,
)
from app.models.company import Company
from app.schemas.survey import (
    PublicQuestion,
    PublicSurvey,
    ResponseAck,
    ResponseSubmission,
)
from app.routers.surveys import (
    _resolve_study_participant,
    _validate_answer_for_type,
)
from app.services.survey_quotas import get_status as get_quota_status

router = APIRouter(prefix="/r", tags=["public_surveys"])


def _resolve_live_link(token: str, db: Session) -> tuple[SurveyLink, Survey]:
    """Resolve a token → (link, survey) or raise a constant-time 404.

    Shared by both GET and POST so the response shape on failure is
    indistinguishable across unhappy paths.
    """

    link = db.query(SurveyLink).filter(SurveyLink.token == token).first()
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

    survey = db.query(Survey).filter(Survey.id == link.survey_id).first()
    if not survey or survey.status != "live":
        raise HTTPException(status_code=404, detail="Survey not available")

    return link, survey


@router.get("/{token}", response_model=PublicSurvey)
def get_public_survey(token: str, db: Session = Depends(get_db)) -> PublicSurvey:
    link, survey = _resolve_live_link(token, db)

    questions = (
        db.query(SurveyQuestion)
        .filter(
            SurveyQuestion.survey_id == survey.id,
            SurveyQuestion.deprecated_at.is_(None),
        )
        .order_by(SurveyQuestion.sort_order)
        .all()
    )

    return PublicSurvey(
        name=survey.name,
        description=survey.description,
        is_anonymous=link.is_anonymous,
        questions=[
            PublicQuestion(
                id=q.id,
                sort_order=q.sort_order,
                type=q.type,  # type: ignore[arg-type]
                prompt=q.prompt,
                is_required=q.is_required,
                config=q.config_dict,
            )
            for q in questions
        ],
    )


@router.post(
    "/{token}/responses",
    response_model=ResponseAck,
    status_code=status.HTTP_201_CREATED,
)
def submit_public_response(
    token: str,
    body: ResponseSubmission,
    db: Session = Depends(get_db),
):
    """Public submission endpoint. Token in the URL takes precedence over
    `body.link_token` — clients can set body.link_token to "" if they like."""

    link, survey = _resolve_live_link(token, db)
    study = db.query(Study).filter(Study.id == survey.study_id).first()
    if not study:
        raise HTTPException(status_code=404, detail="Survey not available")

    # Sprint 12: workspace-level survey quota check. Hard cap — no overage.
    # Constant-time-ish response shape: "Survey is not available" so the
    # respondent flow doesn't leak workspace billing state.
    company = (
        db.query(Company).filter(Company.id == survey.company_id).first()
    )
    if company is not None:
        try:
            quota = get_quota_status(db, company)
            if quota.is_over_response_cap and body.is_complete:
                raise HTTPException(status_code=404, detail="Survey is not available")
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — never let a quota lookup take down a submission
            pass

    participant = _resolve_study_participant(
        db,
        study,
        magic_token=body.magic_token,
        email=body.email,
        display_name=body.display_name,
        is_anonymous=link.is_anonymous,
    )

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

    if body.is_complete:
        answered_ids = {a.question_id for a in body.answers}
        for q in questions_by_id.values():
            if q.is_required and q.id not in answered_ids:
                raise HTTPException(
                    status_code=422, detail=f"Required question missing: {q.id}"
                )

    now = datetime.now(timezone.utc)
    response = SurveyResponse(
        survey_id=survey.id,
        company_id=survey.company_id,
        study_participant_id=participant.id if participant else None,
        link_id=link.id,
        completed_at=now if body.is_complete else None,
        submission_metadata=(
            json.dumps(body.submission_metadata) if body.submission_metadata else None
        ),
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
                value_choice_ids=(
                    json.dumps(ans.value_choice_ids) if ans.value_choice_ids else None
                ),
                time_to_answer_ms=ans.time_to_answer_ms,
            )
        )

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
