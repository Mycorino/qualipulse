"""Fire-and-forget AI usage logging — never raises, never breaks caller flow."""

from sqlalchemy.orm import Session

from app.models.usage import AIUsageLog

# ── Pricing constants (USD per unit) ─────────────────────────────────────────
CLAUDE_INPUT_PER_TOKEN = 0.000003      # $3 per 1M input tokens
CLAUDE_OUTPUT_PER_TOKEN = 0.000015     # $15 per 1M output tokens
WHISPER_PER_SECOND = 0.0001            # $0.006 per minute = $0.0001 per second
TTS_PER_CHARACTER = 0.000015           # $15 per 1M characters


def log_claude_usage(
    db: Session,
    response,  # Anthropic Message response object
    operation: str,
    company_id: int | None = None,
    project_id: int | None = None,
    participant_id: int | None = None,
) -> None:
    """Log Claude API usage from an Anthropic response object."""
    try:
        usage = response.usage
        cost = (
            (usage.input_tokens * CLAUDE_INPUT_PER_TOKEN)
            + (usage.output_tokens * CLAUDE_OUTPUT_PER_TOKEN)
        )
        db.add(
            AIUsageLog(
                company_id=company_id,
                project_id=project_id,
                participant_id=participant_id,
                operation=operation,
                model=getattr(response, "model", "claude-sonnet-4-20250514"),
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cost_usd=cost,
            )
        )
        db.commit()
    except Exception:
        pass  # Never let logging break the main flow


def log_tts_usage(
    db: Session,
    text: str,
    company_id: int | None = None,
    project_id: int | None = None,
    participant_id: int | None = None,
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
    company_id: int | None = None,
    project_id: int | None = None,
    participant_id: int | None = None,
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
