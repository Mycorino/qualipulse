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
from app.services import ai_models

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
    from app.config import settings
    from app.services._clients import get_anthropic_client
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

    prompt = f"""<role>
You are a qualitative-research translator. The original transcript IS the data; this \
translation is a reading aid for a researcher who does not speak the source language. \
Your single most important job is to preserve the participant's voice so the researcher \
can feel what the participant felt. You are NOT polishing, summarising, or "improving" \
their grammar.
</role>

<rules>
PRESERVE — these are evidence, not noise:
- Hedges ("kind of", "I guess", "sort of", "I mean")
- Fillers when they signal hesitation ("um", "you know", "like" in mid-sentence)
- Colloquialisms, slang, and informal register
- Emotional tone (frustration, excitement, resignation, sarcasm)
- Repetition, self-correction, and trailing-off ("it was just… yeah")
- Register: a casual speaker stays casual in {target_name}; a formal speaker stays formal.

DO NOT:
- Fix the speaker's grammar.
- Make their sentences clearer than they were.
- Combine fragmented thoughts into a polished sentence.
- Translate word-for-word at the cost of natural {target_name} — find the equivalent \
register, not the equivalent dictionary entry.
- Add or remove any information.
- "Soften" strong language — if they swore, they swore in {target_name} too.

PASS-THROUGH:
- If a turn is already in {target_name}, return it byte-identical.
- Empty strings stay empty.

ANTI-EXAMPLE (REJECT):
Source (FR): "Bah… je sais pas trop, c'est un peu chiant en fait."
BAD: "I do not know; it is somewhat unpleasant."
GOOD: "Eh… I dunno really, it's kind of annoying actually."
The bad version stripped the hedge ("bah", "un peu"), formalised the register, and lost \
the emotional flavour ("chiant" is stronger than "unpleasant").
</rules>

<input>
{json.dumps(items, ensure_ascii=False)}
</input>

Return ONLY a JSON array with the same length and order. Each item:
{{"id": "<id>", "question": "<translated>", "response": "<translated>"}}"""

    client = get_anthropic_client(180.0)
    response = client.messages.create(
        model=ai_models.sonnet(),
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
