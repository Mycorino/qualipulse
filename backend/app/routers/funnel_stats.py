"""Funnel analytics endpoint — derives signup → activation → paid
conversion stats from existing tables. No new event table; everything
is reconstructible from Companies / Projects / Participants /
WorkspaceSubscriptions.

Read-only, admin-gated. Designed to power a simple internal dashboard
that answers the questions:
- Where in the funnel are users dropping off?
- How long does it take from signup to first interview?
- What % of users who hit the paywall convert?
- Are cohorts trending up or down by signup week?

Most interesting metric: **median time from signup to first completed
participant**. That's the activation latency — if it's >24h, the
onboarding is too slow; if it's <2h, we have product-market fit on
that step.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.company import Company
from app.models.interview import Participant
from app.models.project import Project
from app.routers.admin import require_admin

router = APIRouter(prefix="/admin/funnel", tags=["admin-funnel"])


def _safe_rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _median_minutes(deltas: list[float]) -> Optional[float]:
    """Median of timedelta-in-minutes values. None when no samples."""
    if not deltas:
        return None
    return round(median(deltas), 2)


def _start_of_iso_week(d: datetime) -> datetime:
    """Monday 00:00 UTC of the ISO week containing d."""
    monday = d - timedelta(days=d.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/stats")
def funnel_stats(
    days: int = Query(
        default=90,
        ge=1,
        le=730,
        description="Lookback window in days (default 90, max 730).",
    ),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Top-level funnel snapshot + weekly cohorts."""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)

    # ── Cohort: all signups within the lookback window ─────────────────────
    companies = (
        db.query(Company)
        .filter(Company.created_at >= cutoff)
        .all()
    )

    # ── Step totals ────────────────────────────────────────────────────────
    signups = len(companies)
    onboarded = sum(1 for c in companies if c.onboarding_completed)
    email_verified = sum(1 for c in companies if c.email_verified)
    has_ever_paid = sum(1 for c in companies if c.has_ever_paid)

    company_ids = [c.id for c in companies]
    studies_created = 0
    if company_ids:
        studies_created = (
            db.query(func.count(Project.id))
            .filter(
                Project.company_id.in_(company_ids),
                Project.is_demo.is_(False),
            )
            .scalar()
            or 0
        )

    # First link per workspace = signal of "ready to share."
    workspaces_with_link = 0
    if company_ids:
        from app.models.interview import InterviewLink

        workspaces_with_link = (
            db.query(func.count(func.distinct(Project.company_id)))
            .join(InterviewLink, InterviewLink.project_id == Project.id)
            .filter(
                Project.company_id.in_(company_ids),
                Project.is_demo.is_(False),
            )
            .scalar()
            or 0
        )

    # Completed participants total + first-per-workspace activation.
    participants_completed = 0
    first_participant_workspaces = 0
    workspaces_3plus = 0
    workspaces_10plus = 0
    if company_ids:
        completed_per_workspace = (
            db.query(
                Project.company_id,
                func.count(Participant.id).label("n"),
            )
            .join(Participant, Participant.project_id == Project.id)
            .filter(
                Project.company_id.in_(company_ids),
                Project.is_demo.is_(False),
                Participant.status == "completed",
            )
            .group_by(Project.company_id)
            .all()
        )
        participants_completed = sum(row.n for row in completed_per_workspace)
        first_participant_workspaces = sum(
            1 for row in completed_per_workspace if row.n >= 1
        )
        workspaces_3plus = sum(
            1 for row in completed_per_workspace if row.n >= 3
        )
        workspaces_10plus = sum(
            1 for row in completed_per_workspace if row.n >= 10
        )

    # ── Time-to-X medians (in minutes) ─────────────────────────────────────
    # Activation latency is the headline metric — how long from signup
    # until the first participant completes.
    activation_deltas: list[float] = []
    onboarding_deltas: list[float] = []
    paid_deltas: list[float] = []

    for company in companies:
        if not company.created_at:
            continue
        # signup → first participant completed
        first_completed = (
            db.query(func.min(Participant.completed_at))
            .join(Project, Participant.project_id == Project.id)
            .filter(
                Project.company_id == company.id,
                Project.is_demo.is_(False),
                Participant.status == "completed",
            )
            .scalar()
        )
        if first_completed:
            delta_min = (first_completed - company.created_at).total_seconds() / 60
            if delta_min >= 0:
                activation_deltas.append(delta_min)

        # signup → onboarding_completed approximation — we don't store
        # the timestamp of onboarding completion explicitly, so we use
        # the first non-demo project's created_at as a proxy. Reasonable
        # because acceptStudy in Welcome.tsx is the onboarding-completion
        # action.
        first_project_created = (
            db.query(func.min(Project.created_at))
            .filter(
                Project.company_id == company.id,
                Project.is_demo.is_(False),
            )
            .scalar()
        )
        if first_project_created and company.onboarding_completed:
            delta_min = (
                first_project_created - company.created_at
            ).total_seconds() / 60
            if delta_min >= 0:
                onboarding_deltas.append(delta_min)

        # signup → has_ever_paid (we don't store the exact paid timestamp,
        # so this is approximate — use updated_at on WorkspaceSubscription
        # if available, otherwise skip)
        if company.has_ever_paid:
            from app.models.billing import WorkspaceSubscription

            first_sub = (
                db.query(func.min(WorkspaceSubscription.created_at))
                .filter(WorkspaceSubscription.workspace_id == company.id)
                .scalar()
            )
            if first_sub:
                delta_min = (first_sub - company.created_at).total_seconds() / 60
                if delta_min >= 0:
                    paid_deltas.append(delta_min)

    # ── Cohorts by signup week ─────────────────────────────────────────────
    cohorts: dict[str, dict[str, int]] = {}
    for company in companies:
        if not company.created_at:
            continue
        week_start = _start_of_iso_week(company.created_at).date().isoformat()
        bucket = cohorts.setdefault(
            week_start,
            {
                "week_start": week_start,
                "signups": 0,
                "onboarded": 0,
                "first_participant": 0,
                "paid": 0,
            },
        )
        bucket["signups"] += 1
        if company.onboarding_completed:
            bucket["onboarded"] += 1
        if company.has_ever_paid:
            bucket["paid"] += 1

    # Backfill first_participant per week (separate query).
    if company_ids:
        rows = (
            db.query(
                Company.id,
                func.min(Participant.completed_at).label("first_completed"),
            )
            .join(Project, Project.company_id == Company.id)
            .join(Participant, Participant.project_id == Project.id)
            .filter(
                Company.id.in_(company_ids),
                Project.is_demo.is_(False),
                Participant.status == "completed",
            )
            .group_by(Company.id)
            .all()
        )
        company_by_id = {c.id: c for c in companies}
        for row in rows:
            company = company_by_id.get(row.id)
            if not company or not company.created_at:
                continue
            week_start = (
                _start_of_iso_week(company.created_at).date().isoformat()
            )
            if week_start in cohorts:
                cohorts[week_start]["first_participant"] += 1

    cohort_list = sorted(cohorts.values(), key=lambda c: c["week_start"])

    return {
        "generated_at": now.isoformat(),
        "window_days": days,
        "totals": {
            "signups": signups,
            "onboarded": onboarded,
            "email_verified": email_verified,
            "studies_created": studies_created,
            "workspaces_with_link": workspaces_with_link,
            "first_participant_workspaces": first_participant_workspaces,
            "workspaces_3plus_completed": workspaces_3plus,
            "workspaces_10plus_completed": workspaces_10plus,
            "participants_completed": participants_completed,
            "has_ever_paid": has_ever_paid,
        },
        "rates": {
            "signup_to_onboarded": _safe_rate(onboarded, signups),
            "signup_to_email_verified": _safe_rate(email_verified, signups),
            "onboarded_to_first_participant": _safe_rate(
                first_participant_workspaces, onboarded
            ),
            "first_participant_to_3plus": _safe_rate(
                workspaces_3plus, first_participant_workspaces
            ),
            "first_participant_to_paid": _safe_rate(
                has_ever_paid, first_participant_workspaces
            ),
            "signup_to_paid": _safe_rate(has_ever_paid, signups),
        },
        "time_medians_minutes": {
            "signup_to_onboarded": _median_minutes(onboarding_deltas),
            "signup_to_first_participant": _median_minutes(activation_deltas),
            "signup_to_paid": _median_minutes(paid_deltas),
        },
        "cohorts_by_week": cohort_list,
    }
