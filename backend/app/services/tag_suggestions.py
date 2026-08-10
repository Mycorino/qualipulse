"""AI-assisted qualitative coding: suggested tags + starter codebook.

Two entry points, both researcher-triggered and both strictly
suggestion-only (the researcher's codebook is never mutated without an
explicit accept):

- ``suggest_tags_for_participant`` — hybrid coding pass over one completed
  interview. Deductive core: applies the project's existing codes and
  returns verbatim quotes per code. Bounded inductive margin: may propose
  at most ``MAX_NEW_CODES`` new codes when recurring material has no
  covering code. Every quote is resolved to exact character offsets in the
  raw ``response_transcript`` via ``.find()``; anything the model
  paraphrased is dropped server-side.

- ``suggest_starter_codes`` — proposes 4-6 cross-cutting evidence codes
  from the study scope (objective, decision, audience, guide) for an empty
  codebook. Returns plain proposals; nothing is persisted.
"""
import json
import logging

from sqlalchemy.orm import Session

from app.models.coding import ManualCode, QuoteTag, TagSuggestion
from app.models.interview import Participant
from app.models.project import Project
from app.services import ai_models

logger = logging.getLogger(__name__)

MAX_NEW_CODES = 2
MAX_SUGGESTIONS = 12

_LANG_NAMES = {"fr": "French", "es": "Spanish", "de": "German", "it": "Italian", "pt": "Portuguese"}


def _language_instruction(language: str) -> str:
    lang = (language or "en").lower()
    if lang == "en":
        return ""
    name = _LANG_NAMES.get(lang, language)
    return (
        f"\n\nIMPORTANT: Write code names and rationales in {name}. "
        "Quotes must stay verbatim in the participant's original language."
    )


def _resolve_offsets(turns_by_index: dict, turn_index, quote: str):
    """Locate a quote in the raw transcripts. Returns (turn, start) or None.

    Tries the turn the model named first, then every turn, so an off-by-one
    turn_index doesn't cost us an otherwise-verbatim quote.
    """
    quote = (quote or "").strip().strip('"“”')
    if len(quote) < 8:
        return None
    candidates = []
    if turn_index in turns_by_index:
        candidates.append(turns_by_index[turn_index])
    candidates.extend(t for t in turns_by_index.values() if t not in candidates)
    for turn in candidates:
        body = turn.response_transcript or ""
        idx = body.find(quote)
        if idx >= 0:
            return turn, idx, quote
    return None


def _study_context(project: Project) -> str:
    parts = [f"Study: {project.name}"]
    if project.research_objective:
        parts.append(f"Objective: {project.research_objective}")
    if getattr(project, "decision_to_inform", None):
        parts.append(f"Decision to inform: {project.decision_to_inform}")
    if getattr(project, "target_customer_description", None):
        parts.append(f"Audience: {project.target_customer_description}")
    return "\n".join(parts)


def suggest_tags_for_participant(
    participant_id: str,
    db: Session,
    language: str = "en",
) -> list[TagSuggestion]:
    """Run the hybrid coding pass and persist pending TagSuggestion rows.

    Re-running replaces this participant's *pending* suggestions (accepted
    and rejected rows are kept as history). Returns the fresh pending list.
    Never raises on model errors — returns [] and logs instead.
    """
    try:
        return _suggest_tags_inner(participant_id, db, language)
    except Exception:
        logger.exception("tag suggestion failed for participant %s", participant_id)
        return []


def _suggest_tags_inner(
    participant_id: str,
    db: Session,
    language: str,
) -> list[TagSuggestion]:
    from app.services._clients import get_anthropic_client
    from app.services.usage_logger import log_claude_usage

    participant = db.query(Participant).filter(Participant.id == participant_id).first()
    if participant is None:
        return []
    project = participant.project

    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    turns_by_index = {t.turn_index: t for t in turns if t.response_transcript}
    if not turns_by_index:
        return []

    codes = (
        db.query(ManualCode)
        .filter(ManualCode.project_id == project.id)
        .order_by(ManualCode.sort_order)
        .all()
    )
    codes_by_lower = {c.name.strip().lower(): c for c in codes}

    transcript_lines = []
    for t in turns:
        transcript_lines.append(f"[turn {t.turn_index}] Interviewer: {t.question_text}")
        if t.response_transcript:
            transcript_lines.append(f"[turn {t.turn_index}] Participant: {t.response_transcript}")
    transcript_text = "\n".join(transcript_lines)

    codebook_text = (
        "\n".join(f"- {c.name}" for c in codes) if codes else "(the codebook is empty)"
    )

    prompt = f"""<role>
You are a qualitative coding assistant doing a first-pass coding of ONE interview transcript
for a researcher. The researcher owns the codebook; you only suggest. Precision beats recall:
a wrong suggestion costs the researcher trust, a missed one costs nothing.
</role>

<context>
{_study_context(project)}
</context>

<codebook>
{codebook_text}
</codebook>

<transcript>
{transcript_text}
</transcript>

<rules>
1. DEDUCTIVE FIRST: suggest tags using the existing codebook codes wherever the participant's
   words genuinely evidence that code. Use the code name EXACTLY as written in the codebook.
2. Quotes must be VERBATIM, character-for-character substrings of a participant answer
   (never the interviewer), 8-240 characters, in the participant's original language.
   Never paraphrase, never merge words across sentences.
3. Quality over quantity: at most {MAX_SUGGESTIONS} suggestions total, and only where the
   evidence is clear. Zero suggestions for a code is fine.
4. NEW CODES (optional, max {MAX_NEW_CODES}): only when recurring material has no covering
   code. A new code needs at least 2 supporting quotes from THIS transcript. Code names are
   cross-cutting evidence categories tied to the research decision (like friction, workaround,
   trust signal), 1-4 words. NEVER propose a code that restates an interview question or a
   guide section topic, and never one synonymous with an existing code.
5. Never use em dashes anywhere; use commas or colons instead.
</rules>

<output_format>
Return ONLY a JSON object, no markdown fences, no preamble:
{{
  "suggestions": [
    {{"code": "<existing codebook name>", "turn_index": <int>, "quote": "<verbatim quote>"}}
  ],
  "new_codes": [
    {{"name": "<new code name>", "rationale": "<one sentence: why this category matters for the decision>",
      "quotes": [{{"turn_index": <int>, "quote": "<verbatim quote>"}}]}}
  ]
}}
</output_format>{_language_instruction(language)}"""

    client = get_anthropic_client(60.0)
    response = client.messages.create(
        model=ai_models.sonnet(),
        max_tokens=1500,
        **ai_models.temperature_kwargs(ai_models.sonnet(), 0.2),
        messages=[{"role": "user", "content": prompt}],
    )
    log_claude_usage(
        db,
        response,
        "tag_suggest",
        company_id=project.company_id,
        project_id=project.id,
        participant_id=participant_id,
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```")).strip()
    result = json.loads(raw)

    # Fresh run replaces pending suggestions; accepted/rejected history stays.
    db.query(TagSuggestion).filter(
        TagSuggestion.participant_id == participant_id,
        TagSuggestion.status == "pending",
    ).delete(synchronize_session=False)

    created: list[TagSuggestion] = []
    seen_slices: set[tuple] = set()

    def _existing_tag_overlaps(turn, code_id, start, end) -> bool:
        return (
            db.query(QuoteTag)
            .filter(
                QuoteTag.turn_id == turn.id,
                QuoteTag.manual_code_id == code_id,
                QuoteTag.start_index < end,
                QuoteTag.end_index > start,
            )
            .first()
            is not None
        )

    # Deductive suggestions against the existing codebook.
    for s in (result.get("suggestions") or [])[:MAX_SUGGESTIONS]:
        if not isinstance(s, dict):
            continue
        code = codes_by_lower.get((s.get("code") or "").strip().lower())
        if code is None:
            continue  # unknown code name: dropped, new codes go through new_codes
        resolved = _resolve_offsets(turns_by_index, s.get("turn_index"), s.get("quote"))
        if resolved is None:
            continue
        turn, start, quote = resolved
        end = start + len(quote)
        slice_key = (turn.id, code.id, start, end)
        if slice_key in seen_slices or _existing_tag_overlaps(turn, code.id, start, end):
            continue
        seen_slices.add(slice_key)
        created.append(
            TagSuggestion(
                participant_id=participant_id,
                turn_id=turn.id,
                manual_code_id=code.id,
                selected_text=quote,
                start_index=start,
                end_index=end,
            )
        )

    # Bounded inductive margin: proposed new codes. Filter dupes/empties
    # BEFORE capping so a wasted slot never suppresses a legitimate code.
    new_codes = [
        nc
        for nc in (result.get("new_codes") or [])
        if isinstance(nc, dict)
        and (nc.get("name") or "").strip()
        and (nc.get("name") or "").strip().lower() not in codes_by_lower
    ]
    for nc in new_codes[:MAX_NEW_CODES]:
        name = nc["name"].strip()
        rationale = (nc.get("rationale") or "").strip() or None
        for q in (nc.get("quotes") or []):
            if not isinstance(q, dict):
                continue
            resolved = _resolve_offsets(turns_by_index, q.get("turn_index"), q.get("quote"))
            if resolved is None:
                continue
            turn, start, quote = resolved
            end = start + len(quote)
            slice_key = (turn.id, name.lower(), start, end)
            if slice_key in seen_slices:
                continue
            seen_slices.add(slice_key)
            created.append(
                TagSuggestion(
                    participant_id=participant_id,
                    turn_id=turn.id,
                    proposed_code_name=name,
                    rationale=rationale,
                    selected_text=quote,
                    start_index=start,
                    end_index=end,
                )
            )

    db.add_all(created)
    db.commit()
    for s in created:
        db.refresh(s)
    return created


def suggest_starter_codes(
    project: Project,
    db: Session,
    language: str = "en",
) -> list[dict]:
    """Propose 4-6 starter codes from the study scope. Persists nothing.

    Returns [{"name", "description", "color"}]. Existing code names are
    excluded server-side. Returns [] on any model failure.
    """
    try:
        return _suggest_starter_codes_inner(project, db, language)
    except Exception:
        logger.exception("starter codebook suggestion failed for project %s", project.id)
        return []


def _suggest_starter_codes_inner(
    project: Project,
    db: Session,
    language: str,
) -> list[dict]:
    from app.routers.coding import PRESET_COLORS
    from app.services._clients import get_anthropic_client
    from app.services.usage_logger import log_claude_usage

    existing = db.query(ManualCode).filter(ManualCode.project_id == project.id).all()
    existing_lower = {c.name.strip().lower() for c in existing}

    questions = sorted(
        [q for q in project.guide_questions if not q.deprecated_at],
        key=lambda q: q.sort_order,
    )
    guide_text = "\n".join(f"- {q.main_question}" for q in questions) or "(no guide yet)"
    existing_text = (
        "\n".join(f"- {c.name}" for c in existing) if existing else "(none)"
    )

    prompt = f"""<role>
You are helping a researcher seed the codebook for a qualitative interview study, before or
during data collection. Codes are the evidence categories they will tag quotes with.
</role>

<context>
{_study_context(project)}
</context>

<interview_guide>
{guide_text}
</interview_guide>

<existing_codes>
{existing_text}
</existing_codes>

<rules>
1. Propose 4-6 codes. Each is a CROSS-CUTTING evidence category tied to the decision the study
   informs: think friction, workaround, trust signal, unmet need, price sensitivity, delight.
2. NEVER propose a code that restates an interview question, a guide section, or a topic label.
   Tagging an answer with the question it answered adds no information.
3. Never duplicate or paraphrase an existing code.
4. Names are 1-4 words. Each code gets a one-sentence description of what evidence belongs in it.
5. Never use em dashes; use commas or colons instead.
</rules>

<output_format>
Return ONLY a JSON object, no markdown fences:
{{"codes": [{{"name": "<code name>", "description": "<one sentence>"}}]}}
</output_format>{_language_instruction(language)}"""

    client = get_anthropic_client(45.0)
    response = client.messages.create(
        model=ai_models.sonnet(),
        max_tokens=700,
        **ai_models.temperature_kwargs(ai_models.sonnet(), 0.4),
        messages=[{"role": "user", "content": prompt}],
    )
    log_claude_usage(
        db,
        response,
        "codebook_suggest",
        company_id=project.company_id,
        project_id=project.id,
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = "\n".join(l for l in raw.split("\n") if not l.strip().startswith("```")).strip()
    result = json.loads(raw)

    used_colors = {c.color for c in existing}
    palette = [c for c in PRESET_COLORS if c not in used_colors] or list(PRESET_COLORS)

    proposals: list[dict] = []
    seen: set[str] = set()
    for i, item in enumerate((result.get("codes") or [])[:6]):
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name or name.lower() in existing_lower or name.lower() in seen:
            continue
        seen.add(name.lower())
        proposals.append(
            {
                "name": name,
                "description": (item.get("description") or "").strip(),
                "color": palette[len(proposals) % len(palette)],
            }
        )
    return proposals
