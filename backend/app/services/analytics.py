"""Funnel analytics — structured event logging for activation + conversion.

We don't ship a Mixpanel/Segment SDK yet. Events are emitted as INFO log
lines in a stable `analytics event=… ` format so they are searchable via
``gcloud logging read`` and easy to forward to BigQuery later by replaying
log archives. Same fire-and-forget contract as ``usage_logger`` — never
raises, never blocks the caller.

Event catalogue (keep this stable — downstream dashboards depend on it):

- ``signup``                  — a Company row was just created
- ``onboarding_completed``    — POST /auth/onboarding flipped the flag
- ``study_created``           — first non-demo Project for a Company
- ``link_shared``             — an InterviewLink was created
- ``participant_completed``   — a Participant transitioned to ``completed``
- ``analysis_viewed``         — researcher opened the Analysis tab (FE-fired)
- ``trial_paywall_hit``       — a feature gate blocked a trial user
- ``paid_converted``          — Stripe subscription went active

Standard properties on every event: ``company_id``, ``plan_id``,
``company_size``, ``use_case``, ``role``, ``days_since_signup``. Event-
specific properties go in ``extra``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.logging_config import logger
from app.models.company import Company


def emit_event(
    event: str,
    company: Company | None = None,
    **extra: Any,
) -> None:
    """Emit one funnel event as a structured INFO log line.

    Swallows every exception — analytics is best-effort and never blocks
    the calling request.
    """
    try:
        props: dict[str, Any] = {"event": event}
        if company is not None:
            props["company_id"] = str(company.id)
            props["plan_id"] = (
                getattr(company, "subscription_tier", None) or "unknown"
            )
            props["company_size"] = company.company_size or ""
            props["use_case"] = company.use_case or ""
            props["role"] = company.role or ""
            created_at = getattr(company, "created_at", None)
            if created_at is not None:
                # `created_at` can be naive UTC (SQLite default) or aware.
                now = datetime.now(timezone.utc)
                ref = (
                    created_at
                    if created_at.tzinfo is not None
                    else created_at.replace(tzinfo=timezone.utc)
                )
                props["days_since_signup"] = max(0, (now - ref).days)
        props.update({k: v for k, v in extra.items() if v is not None})

        # Stable single-line format — easy to grep, easy to parse.
        # `analytics event=signup company_id=… plan_id=… …`
        parts = [f"{k}={_fmt(v)}" for k, v in props.items()]
        logger.info("analytics %s", " ".join(parts))
    except Exception:  # noqa: BLE001 — analytics must never raise.
        # Use bare logger access to avoid recursing if logger itself errored.
        try:
            logger.debug("analytics emit failed", exc_info=True)
        except Exception:
            pass


def _fmt(value: Any) -> str:
    """Render a property value as a single token, quoting if it contains spaces."""
    text = str(value)
    if " " in text or "=" in text:
        # Strip quotes/newlines that would break parsing.
        text = text.replace('"', "'").replace("\n", " ")
        return f'"{text}"'
    return text
