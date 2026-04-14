"""Transcript translation via Claude.

Translates question + response text on every turn for a participant into the
researcher's language. Cached on the InterviewTurn row so we never re-translate.

Design principle: original is the data, translation is a reading aid.
We always preserve the source text; we only fill in `translated_*` fields.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.models.interview import InterviewTurn, Participant

logger = logging.getLogger(__name__)

_LANG_NAMES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
}


def translate_participant(
    participant_id: str,
    db: Session,
    target_language: str,
) -> None:
    """Fire-and-forget: translate all turns for a participant. Never raises."""
    try:
        _translate_participant_inner(participant_id, db, target_language)
    except Exception:
        logger.exception("Translation failed for participant %s", participant_id)


def _translate_participant_inner(
    participant_id: str,
    db: Session,
    target_language: str,
) -> None:
    import anthropic
    from app.config import settings
    from app.services.usage_logger import log_claude_usage

    target_language = (target_language or "").lower().strip()
    if not target_language:
        return

    participant = (
        db.query(Participant).filter(Participant.id == participant_id).first()
    )
    if participant is None:
        return

    turns = sorted(participant.turns, key=lambda t: t.turn_index)

    # Only translate turns that don't already have a cached translation
    # in the target language.
    pending = [
        t for t in turns
        if (t.translation_language != target_language)
        or (t.translated_response is None and t.response_transcript)
        or (t.translated_question is None and t.question_text)
    ]
    if not pending:
        return

    target_name = _LANG_NAMES.get(target_language, target_language)

    # Build a JSON payload — one entry per turn — to translate in a single call.
    items = []
    for t in pending:
        items.append({
            "id": t.id,
            "question": t.question_text or "",
            "response": t.response_transcript or "",
        })

    prompt = f"""You are a professional qualitative research translator. Translate the following interview turns into {target_name}.

PRINCIPLES:
- Preserve the participant's voice: keep hedges ("kind of", "I guess"), fillers when meaningful, colloquialisms, and emotional tone.
- Do NOT polish or summarize. A researcher needs to feel what the participant felt.
- Translate idiomatically, not word-for-word. If a phrase has no direct equivalent, use the closest natural {target_name} phrasing.
- If text is already in {target_name}, return it unchanged.
- Never add or remove information.

INPUT (JSON array of turns):
{json.dumps(items, ensure_ascii=False)}

Return ONLY a JSON array with the same length and order, each item: {{"id": "<id>", "question": "<translated>", "response": "<translated>"}}"""

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=8192,
        temperature=0.2,
        messages=[{"role": "user", "content": prompt}],
    )

    log_claude_usage(
        db,
        response,
        "translation",
        company_id=getattr(participant.project, "company_id", None),
        project_id=participant.project_id,
        participant_id=participant_id,
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    translated = json.loads(raw)
    by_id = {item["id"]: item for item in translated if isinstance(item, dict) and "id" in item}

    for t in pending:
        item = by_id.get(t.id)
        if not item:
            continue
        t.translated_question = item.get("question") or None
        t.translated_response = item.get("response") or None
        t.translation_language = target_language
        # We don't reliably know the source per-turn; leave as None unless the
        # project has a configured language. Caller can fill if needed.

    db.commit()
