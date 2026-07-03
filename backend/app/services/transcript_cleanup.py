"""Transcript ASR sense-check via Claude Haiku.

Whisper occasionally mangles proper nouns and domain terms — "Air France"
becomes "la France", "Lufthansa" becomes "l'Ufthansa", "économie/eco" becomes
"écho". This pass fixes those obvious speech-to-text errors using the study's
own context as a glossary, while preserving the participant's voice.

Design principle (same as translation.py): the original `response_transcript`
IS the data and is never overwritten. The correction lives in
`cleaned_response`, a reading aid that the UI shows and the translator uses as
its source. Cheap by design — runs on Haiku, batched one call per participant.

Fire-and-forget: never raises, so a cleanup failure can't break an interview
or a request.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.models.interview import InterviewTurn, Participant
from app.services import ai_models

logger = logging.getLogger(__name__)


def cleanup_participant(participant_id: str, db: Session) -> None:
    """Fire-and-forget: sense-check every turn for a participant. Never raises."""
    try:
        _cleanup_participant_inner(participant_id, db)
    except Exception:
        logger.exception("Transcript cleanup failed for participant %s", participant_id)


def _build_glossary(project) -> str:
    """Compact study-context block so Haiku knows the canonical spellings."""
    if project is None:
        return ""
    bits = []
    if project.name:
        bits.append(f"Study: {project.name}")
    if getattr(project, "research_objective", None):
        bits.append(f"Objective: {project.research_objective}")
    if getattr(project, "target_customer_description", None):
        bits.append(f"Audience: {project.target_customer_description}")
    if getattr(project, "research_context", None):
        bits.append(f"Context: {project.research_context}")
    return "\n".join(bits)


def _cleanup_participant_inner(participant_id: str, db: Session) -> None:
    from app.services._clients import get_anthropic_client
    from app.services.usage_logger import log_claude_usage

    participant = (
        db.query(Participant).filter(Participant.id == participant_id).first()
    )
    if participant is None:
        return

    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    # Only clean turns that have a transcript, aren't already cleaned, and
    # haven't been hand-edited by a researcher (their edit is authoritative).
    pending = [
        t for t in turns
        if t.response_transcript
        and t.response_transcript.strip()
        and t.cleaned_at is None
        and not t.manually_edited
    ]
    if not pending:
        return

    glossary = _build_glossary(participant.project)

    items = [{"id": t.id, "response": t.response_transcript or ""} for t in pending]

    prompt = f"""<role>
You are a speech-to-text proofreader for qualitative-research transcripts. The \
audio was auto-transcribed and sometimes mangles names and domain terms. Your ONLY \
job is to fix clear transcription errors so the text matches what the participant \
actually said. You are NOT editing, polishing, or summarising.
</role>

<study_context>
Use this to recognise the brands, products, and jargon the participant is likely \
referring to (e.g. an airline study → "la France" almost certainly means "Air France", \
"l'Ufthansa" means "Lufthansa", "écho/éco" means "économie/economy class").
{glossary or "(no extra context provided)"}
</study_context>

<rules>
FIX (clear ASR errors only):
- Misheard proper nouns: brand, company, product, place, and person names.
- Domain homophones the context makes obvious (eco/écho, steward/stayward, etc.).
- Obvious word-boundary mistakes that produced a non-word.

DO NOT:
- Paraphrase, reword, shorten, or "improve" anything.
- Fix grammar, register, or disfluencies — keep every hedge, filler, repetition, \
self-correction and trailing-off exactly as transcribed.
- Change meaning, add, or remove information.
- Re-punctuate beyond what a corrected word requires.
- "Correct" a term unless the study context makes the intended word clear — when \
unsure, LEAVE IT AS-IS.

Keep the same language as the source. If a turn has no clear errors, return it \
byte-identical. Empty stays empty.
</rules>

<input>
{json.dumps(items, ensure_ascii=False)}
</input>

Return ONLY a JSON array, same length and order. Each item:
{{"id": "<id>", "response": "<corrected text>"}}"""

    client = get_anthropic_client(120.0)
    response = client.messages.create(
        model=ai_models.haiku(),
        max_tokens=8192,
        **ai_models.temperature_kwargs(ai_models.haiku(), 0.0),
        messages=[{"role": "user", "content": prompt}],
    )

    log_claude_usage(
        db,
        response,
        "transcript_cleanup",
        company_id=getattr(participant.project, "company_id", None),
        project_id=participant.project_id,
        participant_id=participant_id,
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```")).strip()

    cleaned = json.loads(raw)
    by_id = {item["id"]: item for item in cleaned if isinstance(item, dict) and "id" in item}

    from datetime import datetime
    now = datetime.utcnow()
    for t in pending:
        item = by_id.get(t.id)
        if not item:
            continue
        corrected = (item.get("response") or "").strip()
        # Store the cleaned text; if it came back identical we still stamp
        # cleaned_at so we don't re-run, but only set cleaned_response when it
        # actually differs (keeps "is this turn corrected?" honest for the UI).
        if corrected and corrected != t.response_transcript:
            t.cleaned_response = corrected
        t.cleaned_at = now

    db.commit()
