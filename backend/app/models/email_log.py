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
    #   - trial_half_over    : Day 7 of a 14-day trial
    #   - trial_ending       : Day 12 of a 14-day trial
    event: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
