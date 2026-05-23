"""Wave 3B — scheduled lifecycle-email runner.

Cloud Run scales to zero, so we can't have a persistent worker. Instead
this single endpoint is hit hourly by Cloud Scheduler (or any external
cron). It queries due Companies for each lifecycle email, sends them,
and records the send in ``email_send_log`` so re-runs are idempotent.

The runner is admin-only (X-Admin-Key bearer auth, same pattern as
``/admin/*``) and supports ``?dry_run=true`` so you can see what WOULD
be sent without sending.

The three events handled here:

  - ``day_1_followup``   — 18h after signup, only if ``onboarding_completed``
  - ``trial_half_over``  — 5-7 days remaining on ``trial_ends_at``
  - ``trial_ending``     — 0-2 days remaining on ``trial_ends_at``

Each Company × event combination sends at most once thanks to the
unique constraint on ``email_send_log``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.models.company import Company
from app.models.email_log import EmailSendLog
from app.models.interview import Participant
from app.models.project import Project
from app.routers.admin import require_admin
from app.services.email import (
    send_day_1_followup,
    send_trial_ending,
    send_trial_half_over,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/scheduled-emails", tags=["scheduled-emails"])


# ── Plan suggestion (mirrors Welcome.tsx::planSuggestion) ─────────────────────

_PLAN_BY_SIZE: dict[str, tuple[str, str]] = {
    "1–10": ("Exploration", "€89"),
    "1-10": ("Exploration", "€89"),
    "11–50": ("Team", "€299"),
    "11-50": ("Team", "€299"),
    "51–200": ("Team", "€299"),
    "51-200": ("Team", "€299"),
    "201–1000": ("Agency", "€799"),
    "201-1000": ("Agency", "€799"),
    "1000+": ("Agency", "€799"),
}


def _plan_suggestion(
    company_size: str | None,
) -> tuple[Optional[str], Optional[str]]:
    if not company_size:
        return None, None
    return _PLAN_BY_SIZE.get(company_size.strip(), (None, None))


def _first_project_for(db: Session, company_id: str) -> Project | None:
    """The Company's first non-demo project — what we link to from
    Day-1 and Day-7 emails."""
    return (
        db.query(Project)
        .filter(Project.company_id == company_id, Project.is_demo.is_(False))
        .order_by(Project.created_at.asc())
        .first()
    )


def _interview_count(db: Session, company_id: str) -> int:
    """Total completed participants across all this Company's projects.
    Personalises the Day-7 / Day-12 copy."""
    return (
        db.query(Participant)
        .join(Project, Participant.project_id == Project.id)
        .filter(
            Project.company_id == company_id,
            Project.is_demo.is_(False),
            Participant.status == "completed",
        )
        .count()
    )


def _already_sent(db: Session, company_id: str, event: str) -> bool:
    return (
        db.query(EmailSendLog)
        .filter(
            EmailSendLog.company_id == company_id,
            EmailSendLog.event == event,
        )
        .first()
        is not None
    )


def _record_send(db: Session, company_id: str, event: str) -> bool:
    """Insert the send-log row. Returns False if the unique constraint
    trips (concurrent run / replay) — caller should NOT send in that
    case."""
    log_row = EmailSendLog(
        company_id=company_id,
        event=event,
        sent_at=datetime.utcnow(),
    )
    db.add(log_row)
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


# ── The event handlers ───────────────────────────────────────────────────────

def _process_day_1(
    db: Session, now: datetime, dry_run: bool
) -> tuple[int, int]:
    """Day-1: 18h after signup (and onboarding completed).
    Returns (sent_count, skipped_count)."""
    window_start = now - timedelta(days=7)  # cap how far back we'll catch up
    window_end = now - timedelta(hours=18)
    sent = skipped = 0
    candidates = (
        db.query(Company)
        .filter(
            Company.onboarding_completed.is_(True),
            Company.email_verified.is_(True),  # don't pester unverified
            Company.created_at >= window_start,
            Company.created_at <= window_end,
        )
        .all()
    )
    for company in candidates:
        if _already_sent(db, company.id, "day_1_followup"):
            continue
        project = _first_project_for(db, company.id)
        if project is None:
            # No real study yet — not the right Day-1 message; skip.
            skipped += 1
            continue
        if dry_run:
            sent += 1
            continue
        if not _record_send(db, company.id, "day_1_followup"):
            continue
        try:
            send_day_1_followup(
                to=company.email,
                study_name=project.name,
                project_url=f"{settings.APP_BASE_URL}/projects/{project.id}",
                lang=(company.preferred_language or "en"),
            )
            sent += 1
        except Exception:
            logger.exception(
                "Day-1 email failed for %s; send-log row stays so we don't retry",
                company.email,
            )
    return sent, skipped


def _process_trial_half_over(
    db: Session, now: datetime, dry_run: bool
) -> tuple[int, int]:
    """5-7 days remaining → fire trial_half_over. Window is 2 days so a
    cron blip doesn't drop the trigger."""
    sent = skipped = 0
    horizon_low = now + timedelta(days=5)
    horizon_high = now + timedelta(days=7)
    candidates = (
        db.query(Company)
        .filter(
            Company.onboarding_completed.is_(True),
            Company.email_verified.is_(True),
            Company.trial_ends_at.isnot(None),
            Company.trial_ends_at >= horizon_low,
            Company.trial_ends_at <= horizon_high,
            # Don't email people who already converted.
            or_(
                Company.subscription_status.is_(None),
                Company.subscription_status.notin_(("active", "trialing-paid")),
            ),
        )
        .all()
    )
    for company in candidates:
        if _already_sent(db, company.id, "trial_half_over"):
            continue
        project = _first_project_for(db, company.id)
        if project is None:
            skipped += 1
            continue
        days_left = max(1, (company.trial_ends_at - now).days)
        plan_name, plan_monthly = _plan_suggestion(company.company_size)
        if dry_run:
            sent += 1
            continue
        if not _record_send(db, company.id, "trial_half_over"):
            continue
        try:
            send_trial_half_over(
                to=company.email,
                days_left=days_left,
                interviews_run=_interview_count(db, company.id),
                plan_name=plan_name,
                plan_monthly=plan_monthly,
                project_url=f"{settings.APP_BASE_URL}/projects/{project.id}",
                lang=(company.preferred_language or "en"),
            )
            sent += 1
        except Exception:
            logger.exception(
                "Day-7 email failed for %s; send-log row stays so we don't retry",
                company.email,
            )
    return sent, skipped


def _process_trial_ending(
    db: Session, now: datetime, dry_run: bool
) -> tuple[int, int]:
    """0-2 days remaining → fire trial_ending. Last warm nudge."""
    sent = skipped = 0
    horizon_high = now + timedelta(days=2)
    candidates = (
        db.query(Company)
        .filter(
            Company.onboarding_completed.is_(True),
            Company.email_verified.is_(True),
            Company.trial_ends_at.isnot(None),
            Company.trial_ends_at > now,
            Company.trial_ends_at <= horizon_high,
            or_(
                Company.subscription_status.is_(None),
                Company.subscription_status.notin_(("active", "trialing-paid")),
            ),
        )
        .all()
    )
    for company in candidates:
        if _already_sent(db, company.id, "trial_ending"):
            continue
        days_left = max(1, (company.trial_ends_at - now).days)
        plan_name, plan_monthly = _plan_suggestion(company.company_size)
        if dry_run:
            sent += 1
            continue
        if not _record_send(db, company.id, "trial_ending"):
            continue
        try:
            send_trial_ending(
                to=company.email,
                days_left=days_left,
                interviews_run=_interview_count(db, company.id),
                plan_name=plan_name,
                plan_monthly=plan_monthly,
                billing_url=f"{settings.APP_BASE_URL}/account?tab=billing",
                lang=(company.preferred_language or "en"),
            )
            sent += 1
        except Exception:
            logger.exception(
                "Day-12 email failed for %s; send-log row stays so we don't retry",
                company.email,
            )
    return sent, skipped


# ── The endpoint ─────────────────────────────────────────────────────────────

@router.post("/run")
def run_scheduled_emails(
    dry_run: bool = Query(
        default=False,
        description=(
            "When true, query which emails WOULD be sent but don't "
            "actually send. Counts are reported as if it ran."
        ),
    ),
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Cloud Scheduler hits this hourly. Idempotent, fire-and-forget per
    Company, never blocks on send failures (a failed send leaves the
    log row so we don't loop forever on a bad address)."""
    now = datetime.utcnow()
    day_1_sent, day_1_skipped = _process_day_1(db, now, dry_run)
    half_sent, half_skipped = _process_trial_half_over(db, now, dry_run)
    end_sent, end_skipped = _process_trial_ending(db, now, dry_run)
    return {
        "dry_run": dry_run,
        "ran_at": now.isoformat(),
        "events": {
            "day_1_followup": {"sent": day_1_sent, "skipped": day_1_skipped},
            "trial_half_over": {"sent": half_sent, "skipped": half_skipped},
            "trial_ending": {"sent": end_sent, "skipped": end_skipped},
        },
        "total_sent": day_1_sent + half_sent + end_sent,
    }
