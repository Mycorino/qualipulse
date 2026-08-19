"""Append-only audit log for scheduled lifecycle emails (Wave 3B).

One row per (company × event) — the unique index makes the
``/admin/scheduled-emails/run`` runner idempotent: if Cloud Scheduler
ever fires the endpoint twice in the same window, the second insert
trips the constraint and the email is not sent again.

We deliberately do NOT use ``Company.first_response_email_sent_at`` (Wave
3A's per-event column) here — that column predates the table and is
small enough to leave alone. Future one-off lifecycle emails should go
through this table.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ParticipantEmailLog(Base):
    """Append-only audit log for participant-facing lifecycle emails.

    Mirrors ``EmailSendLog`` but keyed per participant: one row per
    (participant × event), with the unique constraint making the
    interview-reminder pass of ``/admin/scheduled-emails/run`` idempotent
    across replayed or concurrent cron firings.
    """

    __tablename__ = "participant_email_log"
    __table_args__ = (
        UniqueConstraint(
            "participant_id", "event", name="uq_participant_email_log_event"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    participant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Event vocabulary:
    #   - interview_reminder_1 : ~1 day after the participant went idle mid-interview
    #   - interview_reminder_2 : ~2 days after reminder 1, final nudge
    event: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )


class EmailSendLog(Base):
    __tablename__ = "email_send_log"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "event", name="uq_email_send_log_company_event"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Event vocabulary — keep this stable, downstream dashboards rely on
    # the values:
    #   - day_1_followup     : 18h after signup, study-recap nudge
    #   - trial_half_over    : (RETIRED) was Day 7 of the legacy calendar trial
    #   - trial_ending       : (RETIRED) was Day 12 of the legacy calendar trial
    event: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
