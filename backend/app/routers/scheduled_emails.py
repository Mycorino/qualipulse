"""Wave 3B — scheduled lifecycle-email runner.

Cloud Run scales to zero, so we can't have a persistent worker. Instead
this single endpoint is hit hourly by Cloud Scheduler (or any external
cron). It queries due Companies for each lifecycle email, sends them,
and records the send in ``email_send_log`` so re-runs are idempotent.

The runner is admin-only (X-Admin-Key bearer auth, same pattern as
``/admin/*``) and supports ``?dry_run=true`` so you can see what WOULD
be sent without sending.

The events handled here:

  - ``day_1_followup``   — 18h after signup, only if ``onboarding_completed``

Calendar-trial emails (``trial_half_over`` / ``trial_ending``) were
retired alongside the credits-native billing model — credits gate
usage, not days. Their templates remain in ``services.email`` as
dead code in case we revive them, but the cron no longer fires them.

Each Company × event combination sends at most once thanks to the
unique constraint on ``email_send_log``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.models.company import Company
from app.models.email_log import EmailSendLog
from app.models.project import Project
from app.routers.admin import require_admin
from app.services.email import send_day_1_followup

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/scheduled-emails", tags=["scheduled-emails"])


def _first_project_for(db: Session, company_id: str) -> Project | None:
    """The Company's first non-demo project — what we link to from
    the Day-1 email."""
    return (
        db.query(Project)
        .filter(Project.company_id == company_id, Project.is_demo.is_(False))
        .order_by(Project.created_at.asc())
        .first()
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
    return {
        "dry_run": dry_run,
        "ran_at": now.isoformat(),
        "events": {
            "day_1_followup": {"sent": day_1_sent, "skipped": day_1_skipped},
        },
        "total_sent": day_1_sent,
    }
