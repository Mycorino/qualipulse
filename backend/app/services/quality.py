"""Quality scoring persisted to the Participant model.

Includes both a fast heuristic scorer and a Claude-powered AI assessment.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.models.interview import Participant
from app.services import ai_models

logger = logging.getLogger(__name__)

_FILLERS = {"yes", "no", "ok", "okay", "sure", "yep", "nope", "yeah", "nah", "uh", "um"}

# Per-label fallback summary, used only when the model returns a blank summary.
# Persisting a non-empty summary keeps the "summary set ⇔ assessment complete"
# invariant that both the re-run guard and the frontend panel rely on.
_FALLBACK_SUMMARY: dict[str, dict[str, str]] = {
    "en": {
        "low": "Automated review: limited depth — mostly short or evasive answers.",
        "fair": "Automated review: some substance but heavy on generics.",
        "good": "Automated review: usable evidence with at least one concrete example.",
        "strong": "Automated review: rich, specific answers with concrete examples.",
    },
    "fr": {
        "low": "Évaluation automatique : profondeur limitée — réponses courtes ou évasives.",
        "fair": "Évaluation automatique : un peu de matière mais beaucoup de généralités.",
        "good": "Évaluation automatique : témoignage exploitable, au moins un exemple concret.",
        "strong": "Évaluation automatique : réponses riches et précises, exemples concrets.",
    },
}


def _fallback_summary(label: str, language: str) -> str:
    lang = (language or "en").lower()
    table = _FALLBACK_SUMMARY.get(lang, _FALLBACK_SUMMARY["en"])
    return table.get(label, table["fair"])


# The assessment object carries seven fields, three of them lists, so it is
# long by construction. 1024 tokens used to cut a rich interview's reply off
# mid-JSON, and the JSONDecodeError threw the whole (already paid for) pass
# away. Budget for the real shape, then salvage anything that still overruns.
_MAX_ASSESSMENT_TOKENS = 2000

_RETRY_NUDGE = (
    "\n\nYour previous reply ran out of room before the JSON closed. Answer "
    "again with the same shape, but keep the whole object under 250 words: at "
    "most 2 strengths, 2 issues, 3 key takeaways and 2 quotes."
)


def _strip_fences(raw: str) -> str:
    if raw.startswith("```"):
        lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
        return "\n".join(lines).strip()
    return raw


def _truncation_candidates(raw: str) -> list[str]:
    """Repair candidates for a reply cut off mid-JSON by the token cap.

    The model emits fields in prompt order, so the ones that carry the rating
    (score, label, summary) are complete long before a list of takeaways runs
    out of budget. Close the object at the last provably complete value
    instead of losing the whole assessment.

    Two cut points are safe without parsing: a comma proves the value before
    it finished, and a bracket that closes a nested container is itself a
    finished value. Whatever containers are still open at that point get
    closed explicitly.
    """
    stack: list[str] = []
    in_string = False
    escaped = False
    cut = -1
    cut_stack: list[str] = []

    for i, ch in enumerate(raw):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack:
                stack.pop()
            if stack:
                cut, cut_stack = i + 1, list(stack)
        elif ch == "," and stack:
            cut, cut_stack = i, list(stack)

    candidates: list[str] = []
    tail = raw.rstrip()
    if stack and not in_string and not tail.endswith((",", ":")):
        # Cut landed exactly on a value boundary: only the closers are missing.
        candidates.append(tail + "".join(reversed(stack)))
    if cut > 0:
        candidates.append(raw[:cut] + "".join(reversed(cut_stack)))
    return candidates


def _parse_assessment_json(raw: str) -> dict:
    """Parse the model's assessment object, repairing truncation if needed."""
    text = _strip_fences((raw or "").strip())
    start = text.find("{")
    if start > 0:
        text = text[start:]
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    for candidate in _truncation_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        # A salvage that lost the rating itself is not worth keeping: better to
        # retry than to persist a confident-looking half assessment.
        if isinstance(parsed, dict) and parsed.get("quality_label"):
            logger.warning(
                "Recovered a truncated quality assessment (%d chars in, %d kept)",
                len(text),
                len(candidate),
            )
            return parsed

    raise ValueError("assessment JSON could not be parsed or repaired")


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

    If the participant already has a non-empty quality_summary, the function
    returns immediately (assessments are never re-run). A blank summary is
    treated as "not yet assessed" so a degenerate result can't lock the
    participant into a permanent half-assessed state.
    """
    try:
        _run_ai_quality_assessment_inner(participant_id, db, language)
    except Exception:
        logger.exception("AI quality assessment failed for participant %s", participant_id)
        _mark_assessment_failed(participant_id, db)


def _mark_assessment_failed(participant_id: str, db: Session) -> None:
    """Record that the pass ran and came back with nothing.

    Without this stamp the panel cannot tell a failure from an assessment
    still in flight, so it told researchers the evaluation had "finished"
    with no summary written when in fact it had crashed.
    """
    try:
        db.rollback()
        participant = (
            db.query(Participant).filter(Participant.id == participant_id).first()
        )
        if participant is not None and not participant.quality_summary:
            participant.quality_status = "failed"
            db.commit()
    except Exception:
        logger.exception(
            "Could not flag the failed quality assessment for %s", participant_id
        )


def _run_ai_quality_assessment_inner(
    participant_id: str,
    db: Session,
    language: str,
) -> None:
    from app.config import settings
    from app.services._clients import get_anthropic_client
    from app.services.usage_logger import log_claude_usage

    participant = (
        db.query(Participant)
        .filter(Participant.id == participant_id)
        .first()
    )
    if participant is None:
        return

    # Already assessed — never re-run. Guard on a *non-empty* summary: an
    # empty string used to satisfy the old `is not None` check and lock the
    # participant into a permanent "assessment in progress" state (the header
    # badge reads quality_label, the panel reads quality_summary — a blank
    # summary lit the badge while the panel spun forever).
    if participant.quality_summary:
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
        language_instruction = (
            f"\n\nIMPORTANT: Respond entirely in {lang_name}, except \"notable_quotes\" "
            "which must stay verbatim in the participant's original language."
        )

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

<digest>
Besides the quality audit, produce a researcher-facing digest of WHAT this participant said:
- "key_takeaways": 3-5 short bullets capturing the participant's main points, behaviours, and
  motivations. Substance only (what they said), not quality commentary (how well they said it).
  Each bullet is one sentence, concrete, and grounded in the transcript.
- "notable_quotes": up to 3 short VERBATIM quotes (each under 200 characters) worth citing in a
  report. Copy them character-for-character from the participant's answers in their original
  language, never translate or paraphrase them, and never quote the interviewer. If nothing is
  quotable, return an empty list.
Never use em dashes in the takeaways or the summary; use commas or colons instead.
</digest>

<output_format>
Return ONLY a JSON object — no markdown fences, no preamble:
{{
  "quality_score": <float 0.0-1.0>,
  "quality_label": "low" | "fair" | "good" | "strong",
  "summary": "<2-3 sentences. Cite at least one specific moment from the transcript that drove the score.>",
  "strengths": ["<concrete strength tied to a moment>", "..."],
  "issues": ["<concrete issue tied to a moment>", "..."],
  "key_takeaways": ["<what the participant said, one sentence>", "..."],
  "notable_quotes": ["<verbatim participant quote>", "..."]
}}
At most 3 strengths and 3 issues. Keep the whole object under 350 words so it
is never cut off mid-field.
</output_format>{language_instruction}"""

    client = get_anthropic_client(60.0)

    # Two attempts: the first at full budget, the second explicitly asking for
    # a shorter object. Salvage handles most overruns, so the retry only fires
    # when the reply is unusable even after repair.
    result: dict | None = None
    last_error: Exception | None = None
    for attempt in range(2):
        response = client.messages.create(
            model=ai_models.sonnet(),
            max_tokens=_MAX_ASSESSMENT_TOKENS,
            **ai_models.temperature_kwargs(ai_models.sonnet(), 0.3),
            messages=[
                {"role": "user", "content": prompt + (_RETRY_NUDGE if attempt else "")}
            ],
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

        try:
            result = _parse_assessment_json(response.content[0].text)
            break
        except ValueError as exc:
            last_error = exc
            logger.warning(
                "Quality assessment reply unusable for %s (attempt %d of 2, stop_reason=%s)",
                participant_id,
                attempt + 1,
                getattr(response, "stop_reason", None),
            )

    if result is None:
        raise last_error or ValueError("quality assessment produced no usable JSON")

    # Persist all 7 fields
    label = result.get("quality_label", "fair")
    # Never persist a blank summary — it would relight the "in progress" panel
    # while the badge (which reads quality_label) shows a rating. Fall back to
    # the first strength, then a label-derived line, so the assessment is
    # always internally consistent.
    summary = (result.get("summary") or "").strip()
    if not summary:
        strengths = [s for s in (result.get("strengths") or []) if s and s.strip()]
        summary = strengths[0].strip() if strengths else _fallback_summary(label, language)
    # Digest: keep only quotes that are actually verbatim (whitespace-tolerant
    # containment against the raw transcripts) so the report-citable list never
    # carries a paraphrase.
    all_answers = " ".join((t.response_transcript or "") for t in responses)
    normalized_answers = " ".join(all_answers.split())
    takeaways = [s.strip() for s in (result.get("key_takeaways") or []) if s and s.strip()]
    quotes = [
        q.strip()
        for q in (result.get("notable_quotes") or [])
        if q and q.strip() and " ".join(q.split()).strip('"“” ') in normalized_answers
    ]

    participant.quality_score = float(result.get("quality_score", 0))
    participant.quality_label = label
    participant.quality_status = "ok"
    participant.quality_summary = summary
    participant.quality_strengths = json.dumps(result.get("strengths", []))
    participant.quality_issues = json.dumps(result.get("issues", []))
    participant.key_takeaways = json.dumps(takeaways)
    participant.notable_quotes = json.dumps(quotes)
    participant.avg_response_words = round(avg_words, 1)
    participant.short_answer_pct = round(short_pct, 1)
    db.commit()
