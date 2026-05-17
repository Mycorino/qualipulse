"""Survey quota enforcement — Sprint 12.

Three quotas per workspace, all driven by PlanEntitlement values:

  - survey_responses_per_period   : hard cap on completed responses per
                                    billing period. Surveys NEVER touch
                                    the credit ledger (roadmap section 1.6),
                                    they're quota-only.
  - surveys_active_max            : how many non-archived surveys exist.
  - survey_questions_per_survey_max: soft cap per survey, advisory.

Counting:
  - Period responses count `survey_responses` rows where
    `completed_at >= subscription.current_period_start`. If no
    subscription period is set we use a calendar-month rolling window.
  - Active surveys count non-archived surveys regardless of status — a
    draft survey still occupies a slot.

What this service deliberately does NOT do:
  - It does not bill overage (killed in roadmap §5). Hard cap only.
  - It does not double-count partial responses — the response_cap on
    SurveyLink already covers per-link concerns; this is workspace-wide.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.company import Company
from app.models.project import Project
from app.models.survey import Survey, SurveyResponse
from app.services.billing_service import get_current_subscription, get_entitlements


@dataclass
class SurveyQuotaStatus:
    """Snapshot of where a workspace stands on its survey quotas."""

    responses_used: int
    responses_cap: int | None
    surveys_active: int
    surveys_cap: int | None
    questions_per_survey_cap: int | None
    period_start: datetime
    period_end: datetime | None
    # Convenience flags for the frontend nudge banner.
    is_over_response_cap: bool
    is_near_response_cap: bool
    is_over_surveys_cap: bool


def _resolve_period(db: Session, workspace_id: str) -> tuple[datetime, datetime | None]:
    """Return (period_start, period_end) for this workspace.

    If the workspace has a WorkspaceSubscription with current_period_start
    set, we use that — keeps quota math aligned with billing periods.
    Otherwise fall back to a rolling 30-day window ending now, which is
    what Trial and legacy plans get.
    """

    sub = get_current_subscription(db, workspace_id)
    now = datetime.now(timezone.utc)
    if sub and sub.current_period_start:
        return sub.current_period_start, sub.current_period_end
    return now - timedelta(days=30), None


def get_status(db: Session, company: Company) -> SurveyQuotaStatus:
    """Compute the current quota state for a workspace.

    Used by:
      - GET /billing/survey-quota (dashboard nudge)
      - POST /r/:token/responses (gate)
      - Admin override surface
    """

    entitlements = get_entitlements(db, company.id)
    responses_cap = _coerce_int(entitlements.get("survey_responses_per_period"))
    surveys_cap = _coerce_int(entitlements.get("surveys_active_max"))
    questions_cap = _coerce_int(entitlements.get("survey_questions_per_survey_max"))

    period_start, period_end = _resolve_period(db, company.id)

    # Surveys that belong to a seeded demo Study are showcase content, not
    # the user's real research — they must never consume quota, exactly as
    # demo Projects are excluded from the project quota in routers/projects.py.
    demo_study_ids = _demo_study_ids(db, company.id)

    responses_query = db.query(func.count(SurveyResponse.id)).filter(
        SurveyResponse.company_id == company.id,
        SurveyResponse.completed_at.isnot(None),
        SurveyResponse.completed_at >= period_start,
    )
    surveys_query = db.query(func.count(Survey.id)).filter(
        Survey.company_id == company.id, Survey.archived_at.is_(None)
    )
    if demo_study_ids:
        responses_query = responses_query.join(
            Survey, SurveyResponse.survey_id == Survey.id
        ).filter(Survey.study_id.notin_(demo_study_ids))
        surveys_query = surveys_query.filter(Survey.study_id.notin_(demo_study_ids))

    responses_used = responses_query.scalar() or 0
    surveys_active = surveys_query.scalar() or 0

    is_over_response = bool(responses_cap is not None and responses_used >= responses_cap)
    is_near = bool(
        responses_cap is not None
        and not is_over_response
        and responses_used / responses_cap >= 0.8
    )
    is_over_surveys = bool(surveys_cap is not None and surveys_active > surveys_cap)

    return SurveyQuotaStatus(
        responses_used=responses_used,
        responses_cap=responses_cap,
        surveys_active=surveys_active,
        surveys_cap=surveys_cap,
        questions_per_survey_cap=questions_cap,
        period_start=period_start,
        period_end=period_end,
        is_over_response_cap=is_over_response,
        is_near_response_cap=is_near,
        is_over_surveys_cap=is_over_surveys,
    )


def _demo_study_ids(db: Session, company_id: str) -> list[str]:
    """Study ids for this workspace that hold a seeded demo project.

    The demo marker lives on ``Project.is_demo``; a Study is "demo" when it
    contains a demo project. Surveys under such a Study are showcase
    content and are excluded from every quota count.
    """

    rows = (
        db.query(Project.study_id)
        .filter(
            Project.company_id == company_id,
            Project.is_demo.is_(True),
            Project.study_id.isnot(None),
        )
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def _coerce_int(value) -> int | None:
    """Treat None/missing/non-numeric entitlement values as 'unlimited'."""

    if value is None:
        return None
    if isinstance(value, bool):
        return None  # bool snuck in as a misconfig — ignore.
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
