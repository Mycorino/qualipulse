"""Wave 3B — scheduled lifecycle-email runner.

Cloud Run scales to zero, so we can't have a persistent worker. Instead
this single endpoint is hit hourly by Cloud Scheduler (or any external
cron). It queries due Companies for each lifecycle email, sends them,
and records the send in ``email_send_log`` so re-runs are idempotent.

The runner is admin-only (X-Admin-Key bearer auth, same pattern as
``/admin/*``) and supports ``?dry_run=true`` so you can see what WOULD
be sent without sending.

The events handled here:

  - ``day_1_followup``         — 18h after signup, only if ``onboarding_completed``
  - ``interview_reminder_1``   — participant idle mid-interview for ~1 day
  - ``interview_reminder_2``   — final nudge ~2 days after reminder 1

Calendar-trial emails (``trial_half_over`` / ``trial_ending``) were
retired alongside the credits-native billing model — credits gate
usage, not days. Their templates remain in ``services.email`` as
dead code in case we revive them, but the cron no longer fires them.

Each Company × event combination sends at most once thanks to the
unique constraint on ``email_send_log``; participant events use the same
pattern on ``participant_email_log``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.models.company import Company
from app.models.email_log import EmailSendLog, ParticipantEmailLog
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.services.admin_auth import require_service_key
from app.services.email import send_day_1_followup, send_interview_reminder
from app.services.verification import magic_link_url, mint_magic_token

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


# ── Interview reminders (participant-facing) ────────────────────────────────

# Reminder 1 goes out once a participant has been idle mid-interview for
# about a day; reminder 2 (the last) about two days after reminder 1, so the
# two land on different days. Windows are wide because the cron is hourly
# and may skip beats, with catch-up caps so a backlog at rollout (or after
# cron downtime) never blasts weeks-old abandons.
REMINDER_1_MIN_IDLE_HOURS = 22
REMINDER_1_MAX_IDLE_DAYS = 4       # miss the window entirely → no reminders at all
REMINDER_2_MIN_GAP_HOURS = 44      # measured from reminder 1's send
REMINDER_MAX_AGE_DAYS = 10         # absolute stop, measured from started_at
# The emailed magic link must outlive the gap until the participant clicks
# it. 7 days matches RESUME_MAX_IDLE_DAYS in routers/interview.py.
REMINDER_MAGIC_EXPIRY_MINUTES = 7 * 24 * 60


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _record_participant_send(db: Session, participant_id: str, event: str) -> bool:
    """Insert-then-send idempotency, same pattern as ``_record_send``."""
    db.add(
        ParticipantEmailLog(
            participant_id=participant_id,
            event=event,
            sent_at=datetime.utcnow(),
        )
    )
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _process_interview_reminders(
    db: Session, now: datetime, dry_run: bool
) -> tuple[int, int]:
    """Nudge participants who went idle mid-interview, at most twice.

    Only participants with a **verified** email are reminded — the email
    embeds a magic link that re-establishes their interview session, so a
    typo'd unverified address must never receive one.
    Returns (sent_count, skipped_count).
    """
    sent = skipped = 0
    candidates = (
        db.query(Participant, InterviewLink, Project)
        .join(InterviewLink, Participant.link_id == InterviewLink.id)
        .join(Project, Participant.project_id == Project.id)
        .filter(
            Participant.status == "in_progress",
            Participant.email.isnot(None),
            Participant.email_verified.is_(True),
            InterviewLink.is_active.is_(True),
            Project.archived_at.is_(None),
            Project.is_demo.is_(False),
            Participant.started_at >= now - timedelta(days=REMINDER_MAX_AGE_DAYS),
        )
        .all()
    )
    for participant, link, project in candidates:
        # If they finished under another participant row (restarted in a new
        # browser, or after the resume window), don't nag about the old one.
        completed_twin = (
            db.query(Participant.id)
            .filter(
                Participant.link_id == link.id,
                func.lower(Participant.email) == participant.email.lower(),
                Participant.status == "completed",
            )
            .first()
        )
        if completed_twin is not None:
            skipped += 1
            continue

        last_turn_at = (
            db.query(func.max(InterviewTurn.created_at))
            .filter(InterviewTurn.participant_id == participant.id)
            .scalar()
        )
        last_activity = _naive(last_turn_at or participant.started_at)
        idle = now - last_activity

        events = {
            row.event: row
            for row in db.query(ParticipantEmailLog)
            .filter(ParticipantEmailLog.participant_id == participant.id)
            .all()
        }

        event: str | None = None
        final = False
        if "interview_reminder_1" not in events:
            if (
                idle >= timedelta(hours=REMINDER_1_MIN_IDLE_HOURS)
                and idle <= timedelta(days=REMINDER_1_MAX_IDLE_DAYS)
            ):
                event = "interview_reminder_1"
        elif "interview_reminder_2" not in events:
            reminder_1_at = _naive(events["interview_reminder_1"].sent_at)
            if now - reminder_1_at >= timedelta(hours=REMINDER_2_MIN_GAP_HOURS):
                event = "interview_reminder_2"
                final = True
        if event is None:
            continue

        if dry_run:
            sent += 1
            continue
        if not _record_participant_send(db, participant.id, event):
            continue
        try:
            lang = (
                participant.preferred_language or project.language or "en"
            ).lower()[:2]
            magic = mint_magic_token(
                db,
                participant.email,
                link.token,
                expiry_minutes=REMINDER_MAGIC_EXPIRY_MINUTES,
            )
            send_interview_reminder(
                to=participant.email,
                project_name=project.name,
                resume_url=magic_link_url(magic, lang),
                greeting_name=participant.display_name,
                lang=lang,
                final=final,
            )
            sent += 1
        except Exception:
            logger.exception(
                "Interview reminder %s failed for participant %s; "
                "send-log row stays so we don't retry",
                event,
                participant.id,
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
    _: str = Depends(require_service_key),
    db: Session = Depends(get_db),
) -> dict:
    """Cloud Scheduler hits this hourly. Idempotent, fire-and-forget per
    Company, never blocks on send failures (a failed send leaves the
    log row so we don't loop forever on a bad address)."""
    now = datetime.utcnow()
    day_1_sent, day_1_skipped = _process_day_1(db, now, dry_run)
    reminders_sent, reminders_skipped = _process_interview_reminders(
        db, now, dry_run
    )
    return {
        "dry_run": dry_run,
        "ran_at": now.isoformat(),
        "events": {
            "day_1_followup": {"sent": day_1_sent, "skipped": day_1_skipped},
            "interview_reminders": {
                "sent": reminders_sent,
                "skipped": reminders_skipped,
            },
        },
        "total_sent": day_1_sent + reminders_sent,
    }
