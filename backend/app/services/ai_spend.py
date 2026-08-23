"""AI provider spend monitoring: burn-rate alerts and out-of-credit alarms.

Two independent alarms, both aimed at the same failure: waking up to find
the Anthropic or OpenAI balance empty and every interview turn broken.

1. **Burn rate** (checked hourly by the scheduled-emails cron). Sums
   ``AIUsageLog.cost_usd`` and alerts when the rolling 24h spend crosses a
   ceiling, spikes against the trailing week, or when month-to-date is on
   pace to blow the monthly budget. This is the early warning: it fires days
   before the balance actually runs out.

2. **Out of credit** (raised from the API call sites). Neither provider
   exposes a remaining-balance endpoint, but both return an unmistakable
   error once the balance hits zero, and that error is the only signal that
   is never an estimate. See ``note_provider_error``.

Neither path may ever raise into a caller: a monitoring bug must not break
an interview.

Note that ``cost_usd`` is *our* computed estimate from token counts, not an
invoice. It tracks the provider bill closely but will not match it to the
cent, so thresholds should be set with a margin.
"""

from __future__ import annotations

import calendar
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.ops_alert import OpsAlertLog
from app.models.usage import AIUsageLog

logger = logging.getLogger("auto_interview.ai_spend")

# How long a single process stays quiet after raising an out-of-credit alarm.
# Once the balance is empty every subsequent call fails the same way, so
# without this a busy instance would hammer the DB (and SendGrid) on every
# turn. The DB claim below is what makes it correct across instances; this
# just keeps the common case cheap.
_OUT_OF_CREDIT_COOLDOWN_SECONDS = 600
_last_alarm: dict[str, float] = {}
_last_alarm_lock = threading.Lock()

# Spike/projection maths need a few days of the month on the clock before
# they mean anything.
_MIN_DAYS_FOR_PROJECTION = 3.0


# ── Spend summary ────────────────────────────────────────────────────────────

def _month_start(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _sum_cost(db: Session, start: datetime, end: datetime | None = None) -> float:
    q = db.query(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0)).filter(
        AIUsageLog.created_at >= start
    )
    if end is not None:
        q = q.filter(AIUsageLog.created_at < end)
    return float(q.scalar() or 0.0)


def spend_summary(db: Session, now: datetime | None = None) -> dict:
    """Everything the alerts and the ops email need, in one pass.

    ``projected_month`` extrapolates month-to-date over the whole month at
    the current pace. It is deliberately naive (linear), which is the right
    read for a burn rate: it answers "if today repeats, where do we land".
    """
    now = now or datetime.utcnow()
    month_start = _month_start(now)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed_days = max((now - month_start).total_seconds() / 86400.0, 0.5)

    last_24h = _sum_cost(db, now - timedelta(hours=24))
    # The 7 days BEFORE the last 24h, so today is compared against a
    # baseline it is not part of.
    prev_7d_total = _sum_cost(db, now - timedelta(days=8), now - timedelta(hours=24))
    month_to_date = _sum_cost(db, month_start)

    top_operations = [
        {"operation": op, "cost_usd": round(float(cost or 0.0), 4)}
        for op, cost in (
            db.query(
                AIUsageLog.operation,
                func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).label("cost"),
            )
            .filter(AIUsageLog.created_at >= now - timedelta(hours=24))
            .group_by(AIUsageLog.operation)
            .order_by(func.coalesce(func.sum(AIUsageLog.cost_usd), 0.0).desc())
            .limit(5)
            .all()
        )
    ]

    return {
        "now": now,
        "last_24h": last_24h,
        "prev_7d_daily_avg": prev_7d_total / 7.0,
        "month_to_date": month_to_date,
        "projected_month": month_to_date / elapsed_days * days_in_month,
        "elapsed_days": elapsed_days,
        "days_in_month": days_in_month,
        "monthly_budget": float(settings.AI_SPEND_MONTHLY_BUDGET_USD or 0.0),
        "top_operations": top_operations,
    }


def _usd(amount: float) -> str:
    return f"${amount:,.2f}"


def _summary_lines(summary: dict) -> list[str]:
    """The shared body of every burn-rate alert, as plain text lines."""
    budget = summary["monthly_budget"]
    lines = [
        f"Last 24h: {_usd(summary['last_24h'])}",
        f"7-day daily average (excluding today): {_usd(summary['prev_7d_daily_avg'])}",
        f"Month to date: {_usd(summary['month_to_date'])}"
        + (f" of {_usd(budget)} budget" if budget > 0 else ""),
        f"Projected this month at the current pace: {_usd(summary['projected_month'])}",
    ]
    if summary["top_operations"]:
        lines.append("")
        lines.append("Biggest spenders in the last 24h:")
        lines += [
            f"  {row['operation']}: {_usd(row['cost_usd'])}"
            for row in summary["top_operations"]
        ]
    return lines


# ── Idempotency ──────────────────────────────────────────────────────────────

def _claim(db: Session, alert_key: str, kind: str, detail: str) -> bool:
    """Insert the alert-log row. False means someone already claimed this
    key (a replayed cron, a second Cloud Run instance) and the caller must
    NOT send. Insert-then-send, same pattern as the lifecycle emails."""
    db.add(
        OpsAlertLog(
            id=str(uuid.uuid4()),
            alert_key=alert_key,
            kind=kind,
            detail=detail[:2000],
            created_at=datetime.utcnow(),
        )
    )
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


# ── Delivery ─────────────────────────────────────────────────────────────────

def _slack_webhook() -> str:
    # Deliberately NOT falling back to SALES_SLACK_WEBHOOK_URL: a spend alarm
    # in the sales channel is a surprise, and the people who watch that
    # channel are not the people who top up an API balance.
    return settings.AI_SPEND_SLACK_WEBHOOK_URL


def send_ops_alert(subject: str, headline: str, lines: list[str]) -> None:
    """Email + Slack, whichever is configured. Never raises.

    Internal mail, so it is English-only and deliberately plain: this gets
    read on a phone at 2am, not in a browser.
    """
    body = "\n".join(lines)
    logger.warning("OPS ALERT %s | %s | %s", subject, headline, body.replace("\n", " / "))

    recipient = settings.AI_SPEND_ALERT_EMAIL
    if recipient:
        try:
            from app.services.email import send_email

            html_lines = "".join(
                f"<p style='margin:0 0 6px'>{line}</p>" if line else "<p>&nbsp;</p>"
                for line in lines
            )
            html = (
                "<div style=\"font-family:-apple-system,BlinkMacSystemFont,"
                "'Segoe UI',Roboto,sans-serif;font-size:14px;color:#0f172a\">"
                f"<h2 style='font-size:16px;margin:0 0 12px'>{headline}</h2>"
                f"{html_lines}"
                "<p style='margin-top:16px;color:#64748b;font-size:12px'>"
                "Figures are QualiPulse's own estimate from logged token usage, "
                "not a provider invoice. Check the Anthropic and OpenAI consoles "
                "for the authoritative balance."
                "</p></div>"
            )
            sent = send_email(
                to=recipient,
                subject=subject,
                body_html=html,
                body_text=f"{headline}\n\n{body}",
                email_type="transactional",
            )
            if not sent:
                logger.error("Ops alert email to %s was not delivered", recipient)
        except Exception:
            logger.exception("Ops alert email failed")

    webhook = _slack_webhook()
    if webhook:
        try:
            from app.services.slack import _post

            _post(webhook, {"text": f"*{headline}*\n" + body})
        except Exception:
            logger.exception("Ops alert Slack post failed")


# ── Burn-rate checks (hourly cron) ───────────────────────────────────────────

def check_spend_alerts(
    db: Session, now: datetime | None = None, dry_run: bool = False
) -> list[dict]:
    """Evaluate every burn-rate threshold. Returns the alerts that fired.

    Each threshold owns its own key window, so a daily ceiling can fire once
    a day while a monthly budget fires once a month.
    """
    now = now or datetime.utcnow()
    try:
        summary = spend_summary(db, now)
    except Exception:
        logger.exception("Spend summary failed; skipping spend alerts")
        return []

    day = now.strftime("%Y-%m-%d")
    month = now.strftime("%Y-%m")
    last_24h = summary["last_24h"]
    mtd = summary["month_to_date"]
    budget = summary["monthly_budget"]
    avg = summary["prev_7d_daily_avg"]

    candidates: list[tuple[str, str, str]] = []  # (key, subject, headline)

    daily_limit = float(settings.AI_SPEND_DAILY_LIMIT_USD or 0.0)
    if daily_limit > 0 and last_24h >= daily_limit:
        candidates.append((
            f"ai_spend:daily_limit:{day}",
            f"[QualiPulse ops] AI spend {_usd(last_24h)} in 24h, over the {_usd(daily_limit)} ceiling",
            f"AI spend in the last 24h ({_usd(last_24h)}) crossed the daily ceiling of {_usd(daily_limit)}.",
        ))

    multiplier = float(settings.AI_SPEND_SPIKE_MULTIPLIER or 0.0)
    floor = float(settings.AI_SPEND_SPIKE_FLOOR_USD or 0.0)
    if multiplier > 0 and avg > 0 and last_24h >= floor and last_24h >= multiplier * avg:
        candidates.append((
            f"ai_spend:spike:{day}",
            f"[QualiPulse ops] AI spend spike: {_usd(last_24h)} in 24h",
            f"AI spend in the last 24h ({_usd(last_24h)}) is {last_24h / avg:.1f}x the "
            f"7-day daily average of {_usd(avg)}. Worth checking for a runaway loop "
            f"or one very heavy account.",
        ))

    if budget > 0:
        if mtd >= budget:
            candidates.append((
                f"ai_spend:budget_100:{month}",
                f"[QualiPulse ops] AI spend has used the full {_usd(budget)} monthly budget",
                f"Month-to-date AI spend is {_usd(mtd)}, at or past the {_usd(budget)} "
                f"monthly budget, with {summary['days_in_month'] - summary['elapsed_days']:.0f} "
                f"days left in the month. Top up provider credits now if the balance is thin.",
            ))
        elif mtd >= 0.8 * budget:
            candidates.append((
                f"ai_spend:budget_80:{month}",
                f"[QualiPulse ops] AI spend at {mtd / budget * 100:.0f}% of the monthly budget",
                f"Month-to-date AI spend is {_usd(mtd)}, {mtd / budget * 100:.0f}% of the "
                f"{_usd(budget)} monthly budget.",
            ))
        elif (
            summary["elapsed_days"] >= _MIN_DAYS_FOR_PROJECTION
            and summary["projected_month"] >= budget
        ):
            candidates.append((
                f"ai_spend:projection:{month}",
                "[QualiPulse ops] AI spend is on pace to pass the monthly budget",
                f"At the current pace this month lands at {_usd(summary['projected_month'])}, "
                f"over the {_usd(budget)} budget. Month-to-date is {_usd(mtd)}.",
            ))

    # Severity order, so when several thresholds trip in the same pass the
    # subject line is the one that matters most.
    order = {
        "budget_100": 0,
        "daily_limit": 1,
        "spike": 2,
        "budget_80": 3,
        "projection": 4,
    }
    candidates.sort(key=lambda c: order.get(c[0].split(":")[1], 99))

    fired: list[dict] = []
    for key, subject, headline in candidates:
        # Claim every threshold that tripped, even though they share one
        # email: each still gets its own once-per-window silence afterwards.
        if not dry_run and not _claim(db, key, "ai_spend", headline):
            continue
        fired.append({"key": key, "subject": subject, "headline": headline})

    if fired and not dry_run:
        # One email per pass. Two near-identical alerts arriving in the same
        # minute is how people learn to filter these into a folder.
        lines = [alert["headline"] for alert in fired[1:]]
        if lines:
            lines.append("")
        send_ops_alert(
            fired[0]["subject"], fired[0]["headline"], lines + _summary_lines(summary)
        )
    return fired


# ── Out-of-credit alarm (raised from the call sites) ─────────────────────────

# Narrow markers only. A broad match on "billing" or "quota" would fire on
# ordinary rate limits, and an alarm that cries wolf gets muted.
_OUT_OF_CREDIT_CODES = {
    "insufficient_quota",
    "billing_hard_limit_reached",
    "credit_balance_too_low",
}
_OUT_OF_CREDIT_PHRASES = (
    "credit balance",                  # Anthropic: "Your credit balance is too low..."
    "exceeded your current quota",     # OpenAI
    "insufficient_quota",
    "billing hard limit",
    "purchase credits",
)


def _error_parts(exc: BaseException) -> tuple[str, str]:
    """(code, message) pulled from the SDK exception.

    Both SDKs hang the parsed JSON error off ``.body``, which is the reliable
    read: ``str(exc)`` is built by the SDK and its shape has changed between
    versions. Anthropic's billing refusal carries type ``invalid_request_error``
    (indistinguishable from a bad parameter) so the message is what identifies
    it; OpenAI's carries code ``insufficient_quota``. Read both, plus
    ``str(exc)`` as a last resort.
    """
    code = str(getattr(exc, "code", "") or "")
    message = ""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        code = str(err.get("code") or err.get("type") or code or "")
        message = str(err.get("message") or "")
    return code.lower(), f"{message} {exc}".lower()


def is_out_of_credit(exc: BaseException) -> bool:
    """Does this exception mean the provider balance is empty?

    Neither provider exposes a balance, so an exhausted account is only ever
    announced as an error, and matching it means matching text. Kept narrow
    on purpose: an alarm that also fires on ordinary rate limits gets muted,
    and then it is worth nothing on the day it is right.
    """
    try:
        code, message = _error_parts(exc)
        if code in _OUT_OF_CREDIT_CODES:
            return True
        return any(phrase in message for phrase in _OUT_OF_CREDIT_PHRASES)
    except Exception:  # pragma: no cover — never break error handling
        return False


def _cooldown_passed(provider: str) -> bool:
    now = time.monotonic()
    with _last_alarm_lock:
        last = _last_alarm.get(provider)
        if last is not None and now - last < _OUT_OF_CREDIT_COOLDOWN_SECONDS:
            return False
        _last_alarm[provider] = now
    return True


def note_provider_error(provider: str, label: str, exc: BaseException) -> None:
    """Raise the alarm if ``exc`` means we are out of provider credit.

    Called from the API call sites, so it must be cheap and silent for the
    99.9% of errors that are ordinary timeouts. Never raises: the caller is
    already re-raising a real failure and must not be derailed by this.
    """
    try:
        if not is_out_of_credit(exc):
            return
        logger.error(
            "%s API refused the call for lack of credit (op=%s): %s",
            provider, label, exc,
        )
        if not _cooldown_passed(provider):
            return

        from app.database import SessionLocal

        detail = (
            f"{provider} rejected an API call for lack of credit "
            f"(operation: {label}). {str(exc)[:400]}"
        )
        # Hourly key: if the balance stays empty we want a reminder each
        # hour, not one alert and then silence.
        key = f"provider_out_of_credit:{provider}:{datetime.utcnow():%Y-%m-%dT%H}"
        session = SessionLocal()
        try:
            if not _claim(session, key, "provider_out_of_credit", detail):
                return
            lines = [
                f"{provider.title()} is refusing API calls because the account balance is empty.",
                "",
                f"Failing operation: {label}",
                f"Provider error: {str(exc)[:400]}",
                "",
                "Interviews, transcription and analysis are failing right now.",
                "Top up in the provider console, and turn on auto-reload so this "
                "cannot happen again.",
            ]
            send_ops_alert(
                f"[QualiPulse ops] {provider.title()} is OUT OF CREDIT",
                f"{provider.title()} API calls are failing: no credit left",
                lines,
            )
        finally:
            session.close()
    except Exception:  # pragma: no cover — defensive
        logger.exception("Out-of-credit alarm failed")
