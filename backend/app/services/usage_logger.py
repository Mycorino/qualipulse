"""Fire-and-forget AI usage logging — never raises, never breaks caller flow."""

from sqlalchemy.orm import Session

from app.logging_config import logger
from app.models.usage import AIUsageLog

# ── Pricing constants (USD per unit) ─────────────────────────────────────────
WHISPER_PER_SECOND = 0.0001            # $0.006 per minute = $0.0001 per second
TTS_PER_CHARACTER = 0.000015           # $15 per 1M characters

# Claude per-token (input, output) rates by model family — matched on a
# substring of response.model. Opus (the copilot) is $5/$25 per 1M,
# Sonnet $3/$15, Haiku $1/$5. The copilot's per-call cost was being
# undercounted ~40% by the old flat Sonnet rate.
_CLAUDE_RATES: list[tuple[str, float, float]] = [
    ("opus", 0.000005, 0.000025),
    ("sonnet", 0.000003, 0.000015),
    ("haiku", 0.000001, 0.000005),
]
_DEFAULT_RATES = (0.000003, 0.000015)  # fall back to Sonnet pricing

# Prompt-caching multipliers on the input rate.
_CACHE_WRITE_MULT = 1.25
_CACHE_READ_MULT = 0.10


def _claude_rates(model: str) -> tuple[float, float]:
    for family, in_rate, out_rate in _CLAUDE_RATES:
        if family in (model or "").lower():
            return in_rate, out_rate
    return _DEFAULT_RATES


def log_claude_usage(
    db: Session,
    response,  # Anthropic Message response object
    operation: str,
    company_id: str | None = None,
    project_id: str | None = None,
    participant_id: str | None = None,
) -> None:
    """Log Claude API usage from an Anthropic response object.

    Cost is model-aware (Opus/Sonnet/Haiku) and accounts for prompt
    caching — ``usage.input_tokens`` is only the *uncached* remainder, so
    cache reads/writes are priced from their own fields. A debug-free
    INFO line records the cache split so cache hit rate is observable in
    production logs without a schema change.
    """
    try:
        usage = response.usage
        model = getattr(response, "model", "") or ""
        in_rate, out_rate = _claude_rates(model)

        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

        cost = (
            usage.input_tokens * in_rate
            + cache_write * in_rate * _CACHE_WRITE_MULT
            + cache_read * in_rate * _CACHE_READ_MULT
            + usage.output_tokens * out_rate
        )
        db.add(
            AIUsageLog(
                company_id=company_id,
                project_id=project_id,
                participant_id=participant_id,
                operation=operation,
                model=model or "claude-unknown",
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost,
            )
        )
        db.commit()

        logger.info(
            "claude usage op=%s model=%s input=%d output=%d "
            "cache_read=%d cache_write=%d cost=$%.5f",
            operation,
            model,
            usage.input_tokens,
            usage.output_tokens,
            cache_read,
            cache_write,
            cost,
        )
    except Exception:
        # Never let logging break the main flow — but DO roll back, or a
        # failed commit leaves the caller's shared session in
        # PendingRollback and silently poisons every later commit in the
        # same turn (including the remaining usage records).
        try:
            db.rollback()
        except Exception:
            pass


def log_tts_usage(
    db: Session,
    text: str,
    company_id: str | None = None,
    project_id: str | None = None,
    participant_id: str | None = None,
) -> None:
    """Log OpenAI TTS usage based on character count."""
    try:
        chars = len(text)
        cost = chars * TTS_PER_CHARACTER
        db.add(
            AIUsageLog(
                company_id=company_id,
                project_id=project_id,
                participant_id=participant_id,
                operation="tts",
                model="tts-1",
                characters=chars,
                cost_usd=cost,
            )
        )
        db.commit()
    except Exception:
        pass


def log_stt_usage(
    db: Session,
    audio_duration_seconds: float,
    company_id: str | None = None,
    project_id: str | None = None,
    participant_id: str | None = None,
) -> None:
    """Log OpenAI Whisper STT usage based on audio duration."""
    try:
        cost = audio_duration_seconds * WHISPER_PER_SECOND
        db.add(
            AIUsageLog(
                company_id=company_id,
                project_id=project_id,
                participant_id=participant_id,
                operation="stt",
                model="whisper-1",
                audio_seconds=audio_duration_seconds,
                cost_usd=cost,
            )
        )
        db.commit()
    except Exception:
        pass
