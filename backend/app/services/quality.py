"""Quality scoring persisted to the Participant model.

Includes both a fast heuristic scorer and a Claude-powered AI assessment.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.models.interview import Participant

logger = logging.getLogger(__name__)

_FILLERS = {"yes", "no", "ok", "okay", "sure", "yep", "nope", "yeah", "nah", "uh", "um"}


def _score_turns(turns) -> tuple[float | None, str | None]:
    responses = [
        t.response_transcript
        for t in turns
        if t.response_transcript and t.response_transcript.strip()
    ]
    if not responses:
        return None, None

    total = 0.0
    for text in responses:
        words = text.lower().split()
        wc = len(words)
        normalized = text.lower().strip().rstrip(".!?")
        is_filler = normalized in _FILLERS or (wc <= 3 and any(f in normalized for f in _FILLERS))

        if is_filler or wc <= 2:
            score = 0.0
        elif wc <= 8:
            score = 0.2
        elif wc <= 20:
            score = 0.5
        elif wc <= 50:
            score = 0.8
        else:
            score = 1.0
        total += score

    avg = total / len(responses)
    if avg < 0.25:
        label = "low"
    elif avg < 0.5:
        label = "fair"
    elif avg < 0.75:
        label = "good"
    else:
        label = "strong"
    return round(avg, 3), label


def score_participant_heuristic(participant_id: str, db: Session) -> None:
    """Compute and persist quality score for a participant."""
    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        return
    score, label = _score_turns(participant.turns)
    participant.quality_score = score
    participant.quality_label = label
    db.commit()


def run_ai_quality_assessment(
    participant_id: str,
    db: Session,
    language: str = "en",
) -> None:
    """Run Claude-powered quality assessment and persist results to the participant.

    This function is designed to be fire-and-forget: it catches all exceptions
    internally and never raises, so it can be called safely from any context.

    If the participant already has a quality_summary, the function returns
    immediately (assessments are never re-run).
    """
    try:
        _run_ai_quality_assessment_inner(participant_id, db, language)
    except Exception:
        logger.exception("AI quality assessment failed for participant %s", participant_id)


def _run_ai_quality_assessment_inner(
    participant_id: str,
    db: Session,
    language: str,
) -> None:
    import anthropic
    from app.config import settings
    from app.services.usage_logger import log_claude_usage

    participant = (
        db.query(Participant)
        .filter(Participant.id == participant_id)
        .first()
    )
    if participant is None:
        return

    # Already assessed — never re-run
    if participant.quality_summary is not None:
        return

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    responses = [t for t in turns if t.response_transcript]
    if not responses:
        return

    # Build transcript text
    transcript_lines: list[str] = []
    for t in turns:
        transcript_lines.append(f"Interviewer: {t.question_text}")
        if t.response_transcript:
            transcript_lines.append(f"Participant: {t.response_transcript}")
    transcript_text = "\n".join(transcript_lines)

    # Compute basic stats
    word_counts = [len((t.response_transcript or "").split()) for t in responses]
    avg_words = sum(word_counts) / len(word_counts) if word_counts else 0
    short_pct = (
        (sum(1 for wc in word_counts if wc < 10) / len(word_counts) * 100)
        if word_counts
        else 0
    )

    # Language instruction
    language_instruction = ""
    if language and language.lower() != "en":
        lang_names = {"fr": "French", "es": "Spanish", "de": "German", "it": "Italian", "pt": "Portuguese"}
        lang_name = lang_names.get(language.lower(), language)
        language_instruction = f"\n\nIMPORTANT: Respond entirely in {lang_name}."

    prompt = f"""You are a qualitative research expert. Assess the quality of the following interview transcript.

TRANSCRIPT:
{transcript_text}

STATS:
- Total responses: {len(responses)}
- Average words per response: {avg_words:.1f}
- % of short responses (<10 words): {short_pct:.0f}%

Evaluate the participant's engagement and response quality. Consider:
- Are responses substantive and detailed, or superficial/evasive?
- Does the participant give genuine, honest answers or just say yes/no/I don't care?
- Is there emotional authenticity and personal experience in the responses?
- Are there any red flags: repeated one-word answers, obvious disengagement, incoherent responses?

Return ONLY a JSON object with this structure:
{{
  "quality_score": <float 0.0-1.0>,
  "quality_label": <"low"|"fair"|"good"|"strong">,
  "summary": "<2-3 sentences overall assessment>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "issues": ["<issue 1>", "<issue 2>"]
}}

quality_score guide: 0.0-0.25=low, 0.25-0.5=fair, 0.5-0.75=good, 0.75-1.0=strong{language_instruction}"""

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}],
    )

    # Log usage
    log_claude_usage(
        db,
        response,
        "quality",
        company_id=getattr(participant.project, "company_id", None),
        project_id=participant.project_id,
        participant_id=participant_id,
    )

    raw = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()

    result = json.loads(raw)

    # Persist all 7 fields
    participant.quality_score = float(result.get("quality_score", 0))
    participant.quality_label = result.get("quality_label", "fair")
    participant.quality_summary = result.get("summary", "")
    participant.quality_strengths = json.dumps(result.get("strengths", []))
    participant.quality_issues = json.dumps(result.get("issues", []))
    participant.avg_response_words = round(avg_words, 1)
    participant.short_answer_pct = round(short_pct, 1)
    db.commit()
