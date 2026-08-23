"""Append-only log of operational alerts sent to the team.

Ops alerts (AI provider spend, out-of-credit failures) are not tied to a
Company, so they cannot use ``email_send_log``. This table plays the same
role: the unique ``alert_key`` is what makes alerting idempotent across an
hourly cron that may fire twice, and across Cloud Run instances that each
hold their own in-process state.

The key encodes both the alert and its window, e.g.::

    ai_spend:daily_limit:2026-08-23
    ai_spend:monthly_budget_80:2026-08
    provider_out_of_credit:anthropic:2026-08-23T14

so "at most one per day" or "at most one per hour" is expressed by the key
rather than by a query.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text


from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class OpsAlertLog(Base):
    __tablename__ = "ops_alert_log"

    id = Column(String(36), primary_key=True, default=_uuid)
    # Unique per (alert × window) — the idempotency key. See module docstring.
    alert_key = Column(String(200), nullable=False, unique=True, index=True)
    # Coarse family, for querying history: "ai_spend" | "provider_out_of_credit"
    kind = Column(String(50), nullable=False, index=True)
    # Human-readable one-liner, kept so the history is readable on its own.
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
