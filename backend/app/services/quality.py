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

    prompt = f"""<role>
You are a sceptical research-ops reviewer auditing whether THIS participant's transcript \
is usable as evidence for a study. Your reader is a researcher deciding whether to weight \
this participant heavily, lightly, or exclude them. Be honest — inflated scores waste their time.
</role>

<rubric>
Score on four dimensions, then combine:
1. DEPTH — do answers go beyond surface ("it's fine", yes/no) into specific examples, behaviours, stories?
2. SPECIFICITY — concrete people / times / places / numbers, vs. generic claims ("users", "always", "kind of")?
3. INTERNAL CONSISTENCY — do later answers reinforce or contradict earlier ones in a coherent way? \
(Contradiction is OK if it reflects honest complexity; inconsistency that smells like inattention is not.)
4. ENGAGEMENT — does the participant build on the interviewer's follow-ups, or stonewall / drift?

Calibration:
- 0.00-0.25 (low): mostly one-word or evasive answers, no concrete example, possible disengagement.
- 0.25-0.50 (fair): some substance but heavy on generics; usable as background, not as primary evidence.
- 0.50-0.75 (good): at least one concrete story or behaviour; usable for theme support.
- 0.75-1.00 (strong): multiple specific examples, emotional authenticity, builds with follow-ups.

Anti-example (REJECT this scoring):
{{ "quality_score": 0.8, "quality_label": "strong", "summary": "The participant gave engaged answers." }}
Why rejected: vague summary, no rubric evidence, almost certainly inflated. A "strong" rating must \
cite at least one specific moment in the transcript that justifies it.
</rubric>

<transcript>
{transcript_text}
</transcript>

<stats>
- Total responses: {len(responses)}
- Average words per response: {avg_words:.1f}
- Short responses (<10 words): {short_pct:.0f}%
</stats>

<output_format>
Return ONLY a JSON object — no markdown fences, no preamble:
{{
  "quality_score": <float 0.0-1.0>,
  "quality_label": "low" | "fair" | "good" | "strong",
  "summary": "<2-3 sentences. Cite at least one specific moment from the transcript that drove the score.>",
  "strengths": ["<concrete strength tied to a moment>", "..."],
  "issues": ["<concrete issue tied to a moment>", "..."]
}}
</output_format>{language_instruction}"""

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
