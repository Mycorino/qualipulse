"""AI-powered synthesis of all completed interview transcripts for a project."""

import json
import logging
from datetime import datetime

logger = logging.getLogger("auto_interview.analysis")

from app.services._clients import get_anthropic_client
from sqlalchemy.orm import Session

from app.config import settings
from app.models.company import Company
from app.models.interview import AnalysisThemeAnnotation, Participant, ProjectAnalysis
from app.models.memo import ProjectMemo
from app.models.project import Project
from app.services.business_context import full_context_block
from app.services.usage_logger import log_claude_usage
from app.services import ai_models

ANALYSIS_SYSTEM_PROMPT = """\
You are a sceptical senior qualitative researcher reviewing your own work for a hostile PM \
who has read every transcript and will catch any inflation. Your job is not to summarise \
the transcripts — it is to extract only what the evidence actually supports, name what it \
doesn't, and tell the team what to do next.

Stance:
- Treat small samples as small samples. 3-6 participants is anecdotal, not "validated".
- Every pattern claim needs at least 2 distinct participants. If only 1 person said it, \
it's a signal worth noting, not a theme.
- Name participants by identifier when reporting frequency. "Most" without naming is banned.
- Surface disconfirming evidence. If P3 contradicts the theme, say so in the same paragraph.
- Recommendations must be actionable AND falsifiable — describe what success looks like and \
what would prove the recommendation wrong.

Banned phrasing (REJECT before output):
- "users want a great experience", "drive engagement", "leverage", "seamless", "delight"
- Vague frequencies ("many users", "some participants") without naming who
- Themes built on a single quote
- Recommendations that read like motherhood statements ("improve onboarding")

Output: your visible answer is ONE valid JSON object and nothing else — no markdown fences, \
no preamble, no trailing commentary. All reasoning and self-critique belong in your thinking, \
never in the visible answer."""


def _build_transcripts_block(participants: list[Participant]) -> tuple[str, dict[str, dict]]:
    """Build transcript block and a participant metadata map keyed by identifier.

    Returns: (transcript_text, participant_map)
    participant_map: {identifier → {display_name, profession, age_range, country}}
    """
    blocks = []
    participant_map: dict[str, dict] = {}

    for i, p in enumerate(participants, 1):
        identifier = f"P{i}"
        name = p.display_name or f"Participant {i}"
        attrs = []
        if getattr(p, "profession", None):
            attrs.append(f"profession: {p.profession}")
        if getattr(p, "age_range", None):
            attrs.append(f"age: {p.age_range}")
        if getattr(p, "country", None):
            attrs.append(f"country: {p.country}")
        # Surface the quality assessment so the synthesis prompt can flag
        # thin participants by name and downweight their evidence weight.
        q_label = getattr(p, "quality_label", None)
        q_score = getattr(p, "quality_score", None)
        if q_label:
            q_str = f"quality: {q_label}"
            if q_score is not None:
                q_str += f" ({q_score:.2f})"
            attrs.append(q_str)

        # Screener answers: researcher-designed profile variables the
        # participant clicked through before qualifying. Far more
        # study-relevant than the generic demographics, so the model gets
        # them as grounded per-participant context.
        screening = getattr(p, "screening_answers_list", None) or []
        if screening:
            pairs = "; ".join(
                f"{(a.get('question') or '').strip()[:80]} = {(a.get('answer') or '').strip()[:60]}"
                for a in screening
                if a.get("question") and a.get("answer")
            )
            if pairs:
                attrs.append(f"screener: {pairs}")

        attr_str = f" ({', '.join(attrs)})" if attrs else ""
        header = f"--- [{identifier}] {name}{attr_str} ---"

        participant_map[identifier] = {
            "display_name": name,
            "profession": getattr(p, "profession", None),
            "age_range": getattr(p, "age_range", None),
            "country": getattr(p, "country", None),
        }

        turns = sorted(p.turns, key=lambda t: t.turn_index)
        lines = [header]
        for t in turns:
            lines.append(f"Q (turn {t.turn_index}): {t.question_text}")
            if t.response_transcript:
                lines.append(f"A: {t.response_transcript}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks), participant_map


_CODEBOOK_QUOTE_SAMPLE = 4  # sample quotes per code fed to the prompt
_CODEBOOK_MAX_CODES = 12


def _codebook_stats(db: Session, project_id: str, participants: list[Participant]) -> list[dict]:
    """Deterministic per-code stats over the included participants' tags.

    Counts are computed in Python, never by the model, so the report's
    codebook figures are always exact. Only codes with at least one tag
    among the included participants appear. Sorted by tag count desc.
    """
    from app.models.coding import ManualCode, QuoteTag
    from app.models.interview import InterviewTurn

    participant_ids = [p.id for p in participants]
    if not participant_ids:
        return []

    rows = (
        db.query(QuoteTag, InterviewTurn.participant_id)
        .join(InterviewTurn, QuoteTag.turn_id == InterviewTurn.id)
        .filter(InterviewTurn.participant_id.in_(participant_ids))
        .all()
    )
    if not rows:
        return []

    codes = {
        c.id: c
        for c in db.query(ManualCode).filter(ManualCode.project_id == project_id).all()
    }
    by_code: dict[str, dict] = {}
    names_by_id = {p.id: (p.display_name or "Participant") for p in participants}
    for tag, pid in rows:
        code = codes.get(tag.manual_code_id)
        if code is None:
            continue
        entry = by_code.setdefault(
            code.id,
            {
                "code": code.name,
                "color": code.color,
                "tag_count": 0,
                "participant_ids": set(),
                "quotes": [],
            },
        )
        entry["tag_count"] += 1
        entry["participant_ids"].add(pid)
        if len(entry["quotes"]) < _CODEBOOK_QUOTE_SAMPLE:
            entry["quotes"].append(
                {"text": tag.selected_text[:240], "participant": names_by_id.get(pid, "Participant")}
            )

    stats = []
    for entry in by_code.values():
        stats.append(
            {
                "code": entry["code"],
                "color": entry["color"],
                "tag_count": entry["tag_count"],
                "participant_count": len(entry["participant_ids"]),
                "participants_total": len(participants),
                "quotes": entry["quotes"],
            }
        )
    stats.sort(key=lambda s: s["tag_count"], reverse=True)
    return stats[:_CODEBOOK_MAX_CODES]


def _build_codebook_block(stats: list[dict]) -> str:
    """Render researcher-verified codebook evidence for the synthesis prompt.

    An accepted tag is the strongest grounding signal we have: a human
    researcher looked at a specific quote and named the evidence category it
    belongs to. The block instructs the model to engage with these
    categories rather than synthesise past them.
    """
    if not stats:
        return ""
    lines = [
        "RESEARCHER CODEBOOK EVIDENCE (quotes the researcher manually tagged "
        "while reading transcripts — researcher-verified signals, the "
        "strongest evidence tier available):"
    ]
    for s in stats:
        lines.append(
            f"- {s['code']}: tagged in {s['participant_count']}/{s['participants_total']} "
            f"interviews ({s['tag_count']} quotes). Samples:"
        )
        for q in s["quotes"]:
            lines.append(f"    \"{q['text']}\" ({q['participant']})")
    lines.append(
        "Your themes must engage with these categories: where a code's evidence "
        "supports a theme, cite it; if your synthesis contradicts a heavily "
        "tagged category, justify the disagreement explicitly. Do not merely "
        "rename the codes as themes without adding analytical value."
    )
    return "\n".join(lines) + "\n\n"


_SUGGESTION_QUOTE_SAMPLE = 3  # sample quotes per machine-coded candidate category
_SUGGESTION_MAX_CODES = 8


def _suggestion_stats(db: Session, participants: list[Participant]) -> list[dict]:
    """Deterministic per-category stats over PENDING AI tag suggestions.

    Tier 2 evidence: verbatim, offset-verified quotes located by the AI
    coding pass that the researcher has NOT reviewed yet. Kept strictly
    separate from `_codebook_stats` (accepted tags) so machine-coded
    candidates can never masquerade as researcher-verified evidence.
    Grouped by the target code name (existing code or proposed new code).
    """
    from app.models.coding import ManualCode, TagSuggestion

    participant_ids = [p.id for p in participants]
    if not participant_ids:
        return []

    rows = (
        db.query(TagSuggestion)
        .filter(
            TagSuggestion.participant_id.in_(participant_ids),
            TagSuggestion.status == "pending",
        )
        .all()
    )
    if not rows:
        return []

    code_names = {
        c.id: c.name
        for c in db.query(ManualCode)
        .filter(ManualCode.id.in_({r.manual_code_id for r in rows if r.manual_code_id}))
        .all()
    }
    names_by_id = {p.id: (p.display_name or "Participant") for p in participants}
    by_code: dict[str, dict] = {}
    for s in rows:
        name = code_names.get(s.manual_code_id) or (s.proposed_code_name or "").strip()
        if not name:
            continue
        entry = by_code.setdefault(
            name.lower(),
            {"code": name, "quote_count": 0, "participant_ids": set(), "quotes": []},
        )
        entry["quote_count"] += 1
        entry["participant_ids"].add(s.participant_id)
        if len(entry["quotes"]) < _SUGGESTION_QUOTE_SAMPLE:
            entry["quotes"].append(
                {
                    "text": (s.selected_text or "")[:240],
                    "participant": names_by_id.get(s.participant_id, "Participant"),
                }
            )

    stats = [
        {
            "code": e["code"],
            "quote_count": e["quote_count"],
            "participant_count": len(e["participant_ids"]),
            "participants_total": len(participants),
            "quotes": e["quotes"],
        }
        for e in by_code.values()
    ]
    stats.sort(key=lambda s: s["quote_count"], reverse=True)
    return stats[:_SUGGESTION_MAX_CODES]


def _build_suggestion_block(stats: list[dict]) -> str:
    """Render machine-coded candidate evidence for the synthesis prompt.

    Weaker framing than `_build_codebook_block` on purpose: these quotes are
    verbatim and offset-verified, but no human judged the category, so the
    model is told to treat them as leads to check against the transcripts,
    never as researcher-verified signals.
    """
    if not stats:
        return ""
    lines = [
        "MACHINE-CODED CANDIDATE EVIDENCE (verbatim quotes located by an AI "
        "coding pass, NOT yet reviewed by the researcher, treat as leads to "
        "verify against the transcripts, a weaker signal than researcher "
        "codebook evidence):"
    ]
    for s in stats:
        lines.append(
            f"- {s['code']}: candidate in {s['participant_count']}/{s['participants_total']} "
            f"interviews ({s['quote_count']} quotes). Samples:"
        )
        for q in s["quotes"]:
            lines.append(f"    \"{q['text']}\" ({q['participant']})")
    lines.append(
        "Use these only where the surrounding transcript confirms them. Never "
        "present a machine-coded category as researcher-verified."
    )
    return "\n".join(lines) + "\n\n"


def _set_stage(db: Session, analysis: ProjectAnalysis, stage: str | None, detail: dict | None = None) -> None:
    """Advance the pipeline stage, committed immediately so the polling
    frontend sees progress in near-real-time. Pass stage=None to clear
    (terminal states)."""
    analysis.stage = stage
    analysis.stage_detail = json.dumps(detail) if detail else None
    db.commit()


def _normalize_for_match(text: str) -> str:
    """Lenient normalisation for verbatim-quote matching.

    Lowercase, straighten curly quotes/dashes, and collapse whitespace so that
    trivial punctuation/spacing differences between the model's quote and the
    stored transcript don't read as fabrication — while a genuinely invented
    sentence still fails the substring test.
    """
    if not text:
        return ""
    text = text.lower()
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'),
                 ("”", '"'), ("–", "-"), ("—", "-"), ("…", "...")):
        text = text.replace(a, b)
    return " ".join(text.split())


def _verify_report_quotes(report: dict, participants: list[Participant]) -> tuple[int, int]:
    """Flag every analysis quote as verified against the real transcripts.

    Mutates the report in place, setting ``verified: bool`` on each quote. A
    quote is verified when its text is a substring of the named participant's
    transcript (falling back to *any* participant's transcript when the
    identifier is missing or mismatched). This turns the product's "full quote
    traceability" claim from a prompt request into an enforced mechanism —
    hallucinated evidence is marked so the UI can flag or drop it.

    Returns ``(verified_count, total_count)``.
    """
    # identifier "P{i}" → normalized concatenated participant responses
    by_identifier: dict[str, str] = {}
    all_text_parts: list[str] = []
    for i, p in enumerate(participants, 1):
        joined = " ".join(
            t.response_transcript for t in p.turns if t.response_transcript
        )
        norm = _normalize_for_match(joined)
        by_identifier[f"P{i}"] = norm
        all_text_parts.append(norm)
    all_text = " ".join(all_text_parts)

    def _check(quote: dict) -> bool:
        """Set ``quote['verified']`` from a substring match and return it."""
        needle = _normalize_for_match(quote.get("text") or "")
        if not needle:
            quote["verified"] = False
            return False
        ident = quote.get("participant_identifier")
        haystack = by_identifier.get(ident, "") if ident else ""
        ok = (needle in haystack) or (needle in all_text)
        quote["verified"] = ok
        return ok

    if not isinstance(report, dict):
        return 0, 0

    verified = 0
    total = 0
    # Theme quotes (list of quote objects per theme).
    for theme in report.get("themes") or []:
        if not isinstance(theme, dict):
            continue
        for quote in theme.get("quotes") or []:
            if not isinstance(quote, dict):
                continue
            total += 1
            if _check(quote):
                verified += 1
    # Persona anchor quotes (one per persona) — the persona exhibit must honour
    # the same traceability guarantee as themes, or it's decoration.
    for persona in report.get("personas") or []:
        if not isinstance(persona, dict):
            continue
        aq = persona.get("anchor_quote")
        if isinstance(aq, dict):
            total += 1
            if _check(aq):
                verified += 1
    # Journey stage quotes (one per stage).
    journey = report.get("journey")
    if isinstance(journey, dict):
        for stage in journey.get("stages") or []:
            if not isinstance(stage, dict):
                continue
            q = stage.get("quote")
            if isinstance(q, dict):
                total += 1
                if _check(q):
                    verified += 1
    return verified, total


# ───────────────────────────────────────────────────────────────────────────
# Static prompt blocks (declared once at module load so the prompt prefix
# stays byte-stable across calls — the Anthropic prompt cache rewards a
# longer stable prefix). Dynamic content (transcripts, objective, filters)
# is appended LAST in the user message.
# ───────────────────────────────────────────────────────────────────────────

_ANALYSIS_RULES_BLOCK = """\
<rules>
EVIDENCE CALIBRATION (tie confidence to N — do not exceed the ceiling):
- N=1-2 participants → confidence "low", label findings "anecdotal"
- N=3-5 → confidence "low" or "medium", label findings "directional"
- N=6-9 → confidence "medium", label findings "suggestive"
- N=10+ with thematic saturation → confidence "high"
Recommendations cannot promise certainty the evidence does not support.

THEME RULES:
- Each theme MUST cite ≥2 verbatim quotes from ≥2 DISTINCT participants. \
If only 1 participant supports it, do not call it a theme — drop it or move it \
to "tensions" as a single-voice signal.
- "frequency" is one of: "all" / "most" / "some" / "few". When using \
"most"/"some"/"few", name the supporting participants in the theme summary \
(e.g. "P1, P3, P5 describe …").
- Quote text must be a verbatim substring of a participant response. Do not \
paraphrase, do not stitch sentences together, do not fix grammar.
- Each quote MUST include the participant identifier (e.g. [P1]) from the \
transcript header. participant_identifier is the raw token like "P1" \
(no brackets); participant_display_name is the human name.

JTBD RULES:
- Strict format: "When I [situation], I want to [motivation], so I can [outcome]."
- The outcome must be the user's outcome, not the company's metric.

TENSION RULES:
- A tension is a forced choice or contradiction the participant lives with — \
not a feature gap. Frame as "X says/does this, BUT also Y" with both halves \
grounded in transcript evidence.

RECOMMENDATION RULES:
- Each recommendation is an OBJECT, not a sentence. Fields: action, rationale, \
owner_role, horizon, impact, effort, kpi, falsifier.
- action is imperative and specific — no "consider", "explore", "leverage", no \
motherhood statements. rationale names the behaviour/theme it addresses.
- owner_role is the responsible FUNCTION (Product / Growth / Marketing / CX / \
Research / Ops), never a person and never a participant.
- horizon is one of: "now" (do this week) / "30d" (next sprint) / "60_90d" \
(this quarter) / "later" (needs more evidence first).
- impact and effort are each one of "low" / "medium" / "high". impact = expected \
effect on the study's decision; effort = build/operational cost. Be honest — not \
everything is high-impact / low-effort.
- kpi is one observable metric or threshold that tells you it worked.
- falsifier states what evidence would prove the recommendation wrong.
- Calibrate to N: at low N, prefer "60_90d"/"later" + a "validate first" framing \
over "now".

DATA QUALITY:
- If a participant's transcript is thin (quality: low/fair, or many one-word \
answers), DO NOT use them as a primary source for a theme. You may still cite \
them, but flag the thinness.
- If the sample is too small or too thin to support themes, return fewer themes \
(or zero) and explain in confidence_rationale rather than padding.

PERSONA RULES:
- Produce personas ONLY when the sample supports distinct archetypes. Each persona \
must be grounded_in ≥2 named participants (e.g. ["P1","P4"]). If N<4 or participants \
do not cluster, return "personas": []. An honest empty array beats an invented persona.
- name is an archetype label (≤4 words), never a real or fabricated person's name.
- Every field must trace to what grounded_in participants actually said. Do not \
import stock-persona clichés the transcripts don't support.
- anchor_quote.text must be a verbatim substring of that participant's transcript.
- Do not claim a participant for a persona whose profile they contradict.

JOURNEY RULES:
- Only build a journey when the interviews describe an experience that unfolds over \
time (a process with stages). For attitudinal/opinion studies with no temporal arc, \
set "applicable": false and "stages": []. Do not force a journey.
- 4-6 stages. Derive stages from the experience participants describe, NOT from the \
interview guide's section order.
- emotion is an integer from -2 (frustrated) to +2 (delighted), grounded in tone/words. \
quote.text must be a verbatim substring of that participant's transcript and should \
justify the emotion score.
- pain/opportunity may be empty strings for smooth stages. Do not manufacture friction.
</rules>"""

_ANALYSIS_SCHEMA_BLOCK = """\
<output_format>
Return ONE JSON object with this exact shape:
{
  "summary": "2-3 sentence executive summary. Lead with the most important finding. No marketing language.",
  "themes": [
    {
      "title": "concrete theme name (≤7 words)",
      "summary": "1-2 sentences. Name supporting participants by identifier (e.g. P1, P3).",
      "quotes": [
        {
          "text": "exact verbatim quote from transcript",
          "participant_identifier": "P1",
          "participant_display_name": "participant name",
          "turn_index": 3,
          "question_text": "the question that prompted this response"
        }
      ],
      "frequency": "all | most | some | few",
      "disconfirming_evidence": "Optional. If any participant contradicted or complicated this theme, name them and quote them briefly. Empty string if no contradiction was found."
    }
  ],
  "jobs_to_be_done": [
    {
      "job": "When I [situation], I want to [motivation], so I can [outcome].",
      "insight": "what this reveals about user motivation that wasn't obvious from the literal answer",
      "frequency": "all | most | some | few"
    }
  ],
  "tensions": [
    {
      "tension": "short label (≤6 words)",
      "detail": "Frame as a forced choice or contradiction grounded in transcript evidence. Name participants."
    }
  ],
  "recommendations": [
    {
      "action": "Imperative, specific next move. No 'consider/explore/leverage'.",
      "rationale": "One line: which theme/behaviour it addresses and why now.",
      "owner_role": "Responsible function — Product | Growth | Marketing | CX | Research | Ops.",
      "horizon": "now | 30d | 60_90d | later",
      "impact": "low | medium | high",
      "effort": "low | medium | high",
      "kpi": "The single observable metric or threshold that shows it worked.",
      "falsifier": "What evidence would prove this recommendation wrong."
    }
  ],
  "personas": [
    {
      "name": "Evocative archetype label, ≤4 words (e.g. 'The Reluctant Switcher'). Not a real name.",
      "grounded_in": ["P1", "P4"],
      "one_liner": "One sentence: who they are in this study's context.",
      "segment": "Demographic/behavioural cluster (e.g. 'Designers, <2y tenure'), or empty string if cross-cutting.",
      "goals": ["What they are trying to achieve (user outcome, not company metric)."],
      "frustrations": ["Concrete pains grounded in what these participants said."],
      "behaviours": ["Observable behaviours/workarounds they described."],
      "primary_job": "The dominant JTBD for this persona.",
      "anchor_quote": {
        "text": "verbatim quote that best captures this persona",
        "participant_identifier": "P1"
      }
    }
  ],
  "journey": {
    "applicable": true,
    "label": "Short name for the journey (e.g. 'Switching grocery providers').",
    "stages": [
      {
        "name": "Stage label, ≤4 words.",
        "goal": "What the participant is trying to do at this stage.",
        "emotion": 0,
        "quote": {
          "text": "verbatim quote anchoring this stage's emotional reality",
          "participant_identifier": "P3"
        },
        "pain": "The dominant friction here, or empty string.",
        "opportunity": "The improvement this friction implies, or empty string."
      }
    ]
  },
  "confidence": "low | medium | high",
  "confidence_rationale": "1-2 sentences. State N, response depth, sample diversity, and any quality concerns.",
  "participant_count": <integer>
}
</output_format>

<examples>
ACCEPT (theme):
{
  "title": "Trust earned through unboxing, not advertising",
  "summary": "P1, P3, and P4 describe deciding to repurchase only after a tactile unboxing moment. P2 explicitly disagrees — she repurchased before any package arrived.",
  "frequency": "most",
  "disconfirming_evidence": "P2: 'I'd already ordered the second one before the first one even shipped.'"
}

REJECT (theme — single quote, vague frequency, no participant naming):
{
  "title": "Users want a delightful experience",
  "summary": "Many participants felt the product was great.",
  "frequency": "most",
  "quotes": [{"text": "It's nice."}]
}
Why rejected: marketing-speak title, single fuzzy quote with no attribution, no disconfirming evidence, "many" without naming.

ACCEPT (recommendation):
{
  "action": "Move the price-justification copy above the fold on the product page.",
  "rationale": "Three of six participants (P1, P4, P6) bounced when they had to scroll to find it.",
  "owner_role": "Product",
  "horizon": "30d",
  "impact": "high",
  "effort": "low",
  "kpi": "Add-to-cart rate on the PDP rises; scroll-past-price rate falls.",
  "falsifier": "A follow-up study where 2+ participants ignore the moved copy and still bounce."
}

REJECT (recommendation):
{"action": "Improve the onboarding experience to drive engagement."}
Why rejected: motherhood statement, banned vocabulary, no rationale/owner/horizon/kpi/falsifier.

ACCEPT (persona):
{
  "name": "The Reluctant Switcher",
  "grounded_in": ["P1", "P4"],
  "one_liner": "Long-time incumbent user who only moved after a concrete failure, not marketing.",
  "goals": ["Avoid disruption to a working routine"],
  "frustrations": ["Migration effort", "Fear of losing history"],
  "anchor_quote": {"text": "I only left because it lost my data twice.", "participant_identifier": "P1"}
}

REJECT (persona):
{"name": "Tech-Savvy Millennial", "grounded_in": ["P2"]}
Why rejected: single participant, stock cliché not grounded in transcripts, no anchor quote.

ACCEPT (journey — experiential study):
{"applicable": true, "label": "Switching providers",
 "stages": [{"name": "Trigger", "goal": "Decide something must change", "emotion": -2,
   "quote": {"text": "it lost my data twice", "participant_identifier": "P1"},
   "pain": "Loss of trust", "opportunity": "Proactive incident comms"}]}

REJECT (journey — attitudinal study forced into stages):
{"applicable": true, "stages": [{"name": "Opinion", "goal": "Have a view on the brand", "emotion": 0}]}
Why rejected: no temporal process in the data — should be {"applicable": false, "stages": []}.
</examples>"""


def _lang_instruction(lang: str) -> str:
    """Force the output language for every model-authored text field.

    Verbatim quotes and canonical enum tokens (horizon/impact/effort/emotion/
    applicable) are exempt. Shared by the v1 and refined runs so the field list
    stays in one place as the schema grows.
    """
    if lang == "en":
        return ""
    target = "French" if lang == "fr" else "English"
    return (
        f"\n\nIMPORTANT — OUTPUT LANGUAGE: Write ALL text fields (summary, theme titles, "
        f"theme summaries, JTBD jobs/insights, tension labels/details, recommendation "
        f"action/rationale/owner_role/kpi/falsifier, persona name/one_liner/segment/goals/"
        f"frustrations/behaviours/primary_job, journey label and stage name/goal/pain/opportunity, "
        f"confidence_rationale) in {target}. Keep enum tokens (horizon, impact, effort, emotion, "
        f"applicable) exactly as specified. Verbatim quotes must stay in the original transcript "
        f"language — never translate quotes."
    )


# ── Structured-output schema (mirrors _ANALYSIS_SCHEMA_BLOCK) ────────────────
# Opus 4.8 structured outputs constrain the response to this exact shape, so the
# report is always a valid object — no markdown-fence stripping, no parse-failure
# branch. Only constructs structured outputs supports are used (objects with
# additionalProperties:false + required, arrays, enums, string/integer/boolean).
# NB: `verified` is intentionally ABSENT — the quote verifier adds it post-gen.
def _sobj(props: dict) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": props,
        "required": list(props.keys()),
    }


_S_STR = {"type": "string"}
_S_INT = {"type": "integer"}
_S_BOOL = {"type": "boolean"}
_S_STR_ARR = {"type": "array", "items": {"type": "string"}}
_S_FREQ = {"type": "string", "enum": ["all", "most", "some", "few"]}
_S_LEVEL = {"type": "string", "enum": ["low", "medium", "high"]}
_S_QUOTE = _sobj({
    "text": _S_STR,
    "participant_identifier": _S_STR,
    "participant_display_name": _S_STR,
    "turn_index": _S_INT,
    "question_text": _S_STR,
})
_S_ANCHOR = _sobj({"text": _S_STR, "participant_identifier": _S_STR})

_REPORT_SCHEMA = _sobj({
    "summary": _S_STR,
    "themes": {"type": "array", "items": _sobj({
        "title": _S_STR,
        "summary": _S_STR,
        "quotes": {"type": "array", "items": _S_QUOTE},
        "frequency": _S_FREQ,
        "disconfirming_evidence": _S_STR,
    })},
    "jobs_to_be_done": {"type": "array", "items": _sobj({
        "job": _S_STR, "insight": _S_STR, "frequency": _S_FREQ,
    })},
    "tensions": {"type": "array", "items": _sobj({
        "tension": _S_STR, "detail": _S_STR,
    })},
    "recommendations": {"type": "array", "items": _sobj({
        "action": _S_STR,
        "rationale": _S_STR,
        "owner_role": _S_STR,
        "horizon": {"type": "string", "enum": ["now", "30d", "60_90d", "later"]},
        "impact": _S_LEVEL,
        "effort": _S_LEVEL,
        "kpi": _S_STR,
        "falsifier": _S_STR,
    })},
    "personas": {"type": "array", "items": _sobj({
        "name": _S_STR,
        "grounded_in": _S_STR_ARR,
        "one_liner": _S_STR,
        "segment": _S_STR,
        "goals": _S_STR_ARR,
        "frustrations": _S_STR_ARR,
        "behaviours": _S_STR_ARR,
        "primary_job": _S_STR,
        "anchor_quote": _S_ANCHOR,
    })},
    "journey": _sobj({
        "applicable": _S_BOOL,
        "label": _S_STR,
        "stages": {"type": "array", "items": _sobj({
            "name": _S_STR,
            "goal": _S_STR,
            "emotion": _S_INT,
            "quote": _S_ANCHOR,
            "pain": _S_STR,
            "opportunity": _S_STR,
        })},
    }),
    "confidence": _S_LEVEL,
    "confidence_rationale": _S_STR,
    "participant_count": _S_INT,
})

# Streamed so Opus's longer, thinking-augmented turns don't trip the non-stream
# HTTP-timeout guard, and so max_tokens can stay high without truncating the
# rich report (thinking tokens share the output budget).
_ANALYSIS_MAX_TOKENS = 28000


def _is_output_format_error(exc: Exception) -> bool:
    """True when a request failed because the server rejected output_config /
    the json_schema — so we can retry once without structured output rather than
    fail the whole analysis on a schema issue."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    msg = str(exc).lower()
    hit = any(k in msg for k in ("output_config", "json_schema", "schema", "format"))
    return hit and (status in (400, None))


def _synthesize_response(prompt: str, effort: str = "high"):
    """Run one Opus 4.8 synthesis turn — adaptive thinking + effort + structured
    output, streamed — and return the final Message.

    Structured output is best-effort: if the server rejects the schema we retry
    once without it (thinking + effort + streaming stay on), so a schema issue
    can never take the analysis path down — the model still returns the same JSON
    shape from the prompt contract. Temperature is dropped automatically on Opus
    via ``temperature_kwargs``.
    """
    client = get_anthropic_client()
    model = ai_models.analysis()
    base = dict(
        model=model,
        max_tokens=_ANALYSIS_MAX_TOKENS,
        thinking={"type": "adaptive"},
        system=ANALYSIS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        **ai_models.temperature_kwargs(model, 0.3),
    )
    for use_schema in (True, False):
        output_config = {"effort": effort}
        if use_schema:
            output_config["format"] = {"type": "json_schema", "schema": _REPORT_SCHEMA}
        try:
            with client.messages.stream(output_config=output_config, **base) as stream:
                return stream.get_final_message()
        except Exception as exc:  # noqa: BLE001
            if use_schema and _is_output_format_error(exc):
                logger.warning("structured output rejected; retrying without schema: %s", exc)
                continue
            raise


def _raise_on_bad_stop(response) -> None:
    """Turn a truncated or refused synthesis into a clear failure message."""
    stop = getattr(response, "stop_reason", None)
    if stop == "max_tokens":
        raise ValueError(
            "Analysis output was truncated (hit max_tokens). Try filtering to "
            "a segment or fewer participants."
        )
    if stop == "refusal":
        raise ValueError(
            "The model declined to analyse this material. This is unusual for "
            "research transcripts — contact support if it persists."
        )


def _parse_report(response) -> dict:
    """Extract the report JSON from a (possibly thinking-augmented) response.

    Selects the text block explicitly — with adaptive thinking on, a thinking
    block precedes it, so ``content[0]`` is not the answer. Fence-stripping is a
    belt-and-suspenders fallback for the no-structured-output retry path.
    """
    raw = next(
        (b.text for b in response.content if getattr(b, "type", None) == "text"),
        "",
    ).strip()
    if raw.startswith("```"):
        lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
        raw = "\n".join(lines).strip()
    return json.loads(raw)


def _filter_participants(
    participants: list[Participant],
    filter_by: str | None,
    filter_values: list[str],
) -> list[Participant]:
    """Segment filter. Demographic attributes filter by column value;
    ``filter_by="screening:<question_id>"`` filters by the participant's
    stored screener answer to that question."""
    if not filter_by or not filter_values:
        return participants
    if filter_by.startswith("screening:"):
        question_id = filter_by.split(":", 1)[1]
        result = []
        for p in participants:
            answers = {
                a.get("question_id"): a.get("answer")
                for a in (getattr(p, "screening_answers_list", None) or [])
            }
            if answers.get(question_id) in filter_values:
                result.append(p)
        return result
    result = []
    for p in participants:
        val = getattr(p, filter_by, None)
        if val and val in filter_values:
            result.append(p)
    return result


def run_analysis(
    project_id: str,
    db: Session,
    filter_by: str | None = None,
    filter_values: list[str] | None = None,
    auto_tag: bool = False,
) -> None:
    """Run full synthesis for completed interviews as a staged pipeline.

    Stages (visible to the polling frontend via ProjectAnalysis.stage):
    auto_tagging (optional, when the researcher chose "auto-tag first" in the
    readiness gate) → preparing → synthesizing → verifying. Upserts a
    ProjectAnalysis row. Meant to be called in a background thread.
    """
    filter_values = filter_values or []

    project: Project | None = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return

    all_completed = [p for p in project.participants if p.status == "completed" and p.turns]
    completed = _filter_participants(all_completed, filter_by, filter_values)

    # Create a new versioned analysis row (keep last 5 per project)
    last = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id)
        .order_by(ProjectAnalysis.version.desc())
        .first()
    )
    next_version = (last.version + 1) if last else 1
    analysis = ProjectAnalysis(project_id=project_id, version=next_version)
    db.add(analysis)

    analysis.status = "generating"
    analysis.participant_count = len(completed)
    analysis.report = None
    analysis.error = None
    if filter_by and filter_values:
        analysis.filters = json.dumps({"filter_by": filter_by, "filter_values": filter_values})
    else:
        analysis.filters = None
    db.commit()

    # Prune: keep the 5 most recent versions, but NEVER delete a version
    # that is still load-bearing: shared via a live public link
    # (share_token), annotated by the researcher, or the parent of a kept
    # version (lineage). Silent destruction of a shared report is worse
    # than a few extra rows.
    from app.models.interview import AnalysisThemeAnnotation

    all_versions = (
        db.query(ProjectAnalysis)
        .filter(ProjectAnalysis.project_id == project_id)
        .order_by(ProjectAnalysis.version.desc())
        .all()
    )
    kept_parent_ids = {
        a.parent_version_id for a in all_versions[:5] if a.parent_version_id
    }
    for old in all_versions[5:]:
        if old.share_token or old.id in kept_parent_ids:
            continue
        has_annotations = (
            db.query(AnalysisThemeAnnotation.id)
            .filter(AnalysisThemeAnnotation.analysis_id == old.id)
            .first()
            is not None
        )
        if has_annotations:
            continue
        db.delete(old)
    db.commit()

    try:
        company = db.query(Company).filter(Company.id == project.company_id).first()
        lang = getattr(company, "preferred_language", None) or "en"

        if auto_tag:
            # Researcher confirmed AI coding in the readiness gate: run the
            # hybrid tag-suggestion pass over every included participant that
            # has neither accepted tags nor pending suggestions. Suggestions
            # stay pending (the codebook is never mutated without an explicit
            # accept) and feed the Tier-2 candidate-evidence block below.
            # Per-participant failures are swallowed inside
            # suggest_tags_for_participant so one bad interview never kills
            # the whole run.
            from app.models.coding import QuoteTag, TagSuggestion
            from app.models.interview import InterviewTurn
            from app.services.tag_suggestions import suggest_tags_for_participant

            pids = [p.id for p in completed]
            tagged_pids = {
                pid
                for (pid,) in db.query(InterviewTurn.participant_id)
                .join(QuoteTag, QuoteTag.turn_id == InterviewTurn.id)
                .filter(InterviewTurn.participant_id.in_(pids))
                .distinct()
            } if pids else set()
            suggested_pids = {
                pid
                for (pid,) in db.query(TagSuggestion.participant_id)
                .filter(
                    TagSuggestion.participant_id.in_(pids),
                    TagSuggestion.status == "pending",
                )
                .distinct()
            } if pids else set()
            to_tag = [p for p in completed if p.id not in tagged_pids and p.id not in suggested_pids]
            total = len(to_tag)
            for i, p in enumerate(to_tag):
                _set_stage(db, analysis, "auto_tagging", {"done": i, "total": total})
                suggest_tags_for_participant(p.id, db, language=lang)
            if total:
                _set_stage(db, analysis, "auto_tagging", {"done": total, "total": total})

        _set_stage(db, analysis, "preparing")
        transcripts_block, participant_map = _build_transcripts_block(completed)
        # Business context: the analysis is infinitely more useful when the
        # model knows what the researcher actually sells and who they sell to.
        context_block = full_context_block(company, project)

        objective_block = (
            f"RESEARCH OBJECTIVE:\n{project.research_objective}\n\n"
            if project.research_objective
            else ""
        )

        filter_note = ""
        if filter_by and filter_values:
            filter_note = f"NOTE: This analysis covers only participants filtered by {filter_by} = {', '.join(filter_values)}.\n\n"

        # Researcher-verified evidence: tags the researcher placed (or accepted
        # from AI suggestions), restricted to the participants in this run so
        # segment-filtered analyses only see their own segment's tags.
        codebook_stats = _codebook_stats(db, project_id, completed)
        codebook_block = _build_codebook_block(codebook_stats)

        # Tier-2 evidence: pending AI tag suggestions (offset-verified but
        # not researcher-reviewed), framed strictly weaker than the codebook.
        suggestion_block = _build_suggestion_block(_suggestion_stats(db, completed))

        lang_instruction = _lang_instruction(lang)

        # Static blocks first (rules + schema + examples) → cached prefix.
        # Dynamic blocks last (context, objective, filters, codebook, transcripts).
        prompt = (
            f"{_ANALYSIS_RULES_BLOCK}\n\n"
            f"{_ANALYSIS_SCHEMA_BLOCK}\n\n"
            f"<task>\nSynthesize the interviews below into a research report. "
            f"Apply the rules above without exception. Confidence MUST be calibrated to N "
            f"(N={len(completed)} here).{lang_instruction}\n</task>\n\n"
            f"{context_block}{objective_block}{filter_note}{codebook_block}{suggestion_block}"
            f"<transcripts count=\"{len(completed)}\">\n{transcripts_block}\n</transcripts>\n\n"
            f"Return the JSON object now. participant_count must be {len(completed)}."
        )

        _set_stage(db, analysis, "synthesizing")
        response = _synthesize_response(prompt, effort="high")
        log_claude_usage(db, response, "analysis", company_id=project.company_id, project_id=project_id)
        _raise_on_bad_stop(response)

        # Parse (structured output guarantees a valid object), then verify every
        # quote against the real transcripts so hallucinated evidence is flagged
        # (verified=false) rather than trusted.
        _set_stage(db, analysis, "verifying")
        report_obj = _parse_report(response)
        v_count, v_total = _verify_report_quotes(report_obj, completed)
        if v_total:
            logger.info(
                "analysis quote verification: %d/%d verbatim (project=%s)",
                v_count, v_total, project_id,
            )

        # Deterministic, Python-computed codebook figures ride along in the
        # report so the UI never quotes a model-invented count.
        if codebook_stats:
            report_obj["codebook_stats"] = [
                {k: v for k, v in s.items() if k != "quotes"} for s in codebook_stats
            ]

        analysis.report = json.dumps(report_obj)
        analysis.status = "ready"
        analysis.generated_at = datetime.utcnow()

    except Exception as e:
        analysis.status = "failed"
        analysis.error = str(e)

    analysis.stage = None
    analysis.stage_detail = None
    db.commit()


def run_refined_analysis(project_id: str, new_analysis_id: str, parent_analysis_id: str, db: Session) -> None:
    """Run a researcher-guided refined synthesis, incorporating theme annotations and researcher context.

    Meant to be called in a background thread. Writes result to the new_analysis_id row.
    """
    project: Project | None = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        return

    new_analysis = db.query(ProjectAnalysis).filter(ProjectAnalysis.id == new_analysis_id).first()
    if new_analysis is None:
        return

    parent_analysis = db.query(ProjectAnalysis).filter(ProjectAnalysis.id == parent_analysis_id).first()
    if parent_analysis is None:
        new_analysis.status = "failed"
        new_analysis.error = "Parent analysis not found"
        db.commit()
        return

    try:
        _set_stage(db, new_analysis, "preparing")
        # Load annotations from the parent analysis
        annotations = (
            db.query(AnalysisThemeAnnotation)
            .filter(AnalysisThemeAnnotation.analysis_id == parent_analysis_id)
            .all()
        )

        confirmed = [a for a in annotations if a.status == "confirmed"]
        disputed = [a for a in annotations if a.status == "disputed"]
        needs_evidence = [a for a in annotations if a.status == "needs_evidence"]

        # Build annotation sections
        annotation_sections = []
        annotation_sections.append("RESEARCHER ANNOTATIONS FROM PREVIOUS ANALYSIS:")
        annotation_sections.append(
            "You are producing a refined synthesis. A domain expert has reviewed the previous analysis "
            "and provided the following signals. Incorporate them carefully."
        )
        annotation_sections.append("")

        if confirmed:
            annotation_sections.append("CONFIRMED THEMES (preserve and strengthen):")
            for a in confirmed:
                bullet = f"- {a.theme_title}"
                if a.researcher_note:
                    bullet += f": {a.researcher_note}"
                annotation_sections.append(bullet)
            annotation_sections.append("")

        if disputed:
            annotation_sections.append(
                "DISPUTED THEMES (re-examine — researcher believes these are mis-framed):"
            )
            for a in disputed:
                bullet = f"- {a.theme_title}"
                if a.researcher_note:
                    bullet += f": {a.researcher_note}"
                annotation_sections.append(bullet)
            annotation_sections.append(
                "Each disputed theme includes a researcher note explaining why. Reframe if you agree "
                "with their evidence, but if transcript data strongly supports the original framing, "
                'keep it and add a "researcher_note" field to that theme object explaining the disagreement.'
            )
            annotation_sections.append("")

        if needs_evidence:
            annotation_sections.append(
                "THEMES NEEDING MORE EVIDENCE (only include if 2+ distinct participant quotes support them):"
            )
            for a in needs_evidence:
                bullet = f"- {a.theme_title}"
                if a.researcher_note:
                    bullet += f": {a.researcher_note}"
                annotation_sections.append(bullet)
            annotation_sections.append("")

        researcher_context = parent_analysis.researcher_context or ""
        if researcher_context.strip():
            annotation_sections.append("RESEARCHER CONTEXT (implicit knowledge not visible in transcripts):")
            annotation_sections.append(researcher_context.strip())
            annotation_sections.append("")

        # Project memos — if the researcher has been taking notes while
        # reading transcripts, surface them so the refined run can weave
        # that knowledge into themes instead of ignoring it. We pull the
        # most recent 15 memos to stay under the token budget; older notes
        # are usually stale or already reflected in annotations.
        memos = (
            db.query(ProjectMemo)
            .filter(ProjectMemo.project_id == project_id)
            .order_by(ProjectMemo.updated_at.desc())
            .limit(15)
            .all()
        )
        if memos:
            annotation_sections.append(
                "RESEARCHER MEMOS (notes the researcher wrote while reading "
                "transcripts — treat as soft evidence, not hard facts):"
            )
            for memo in memos:
                # Normalise memo type → short label so Claude sees what kind
                # of note this is (general / theme-linked / tension-linked /
                # jtbd-linked).
                label_map = {
                    "general": "Note",
                    "theme_note": "Theme note",
                    "tension_note": "Tension note",
                    "jtbd_note": "JTBD note",
                }
                label = label_map.get(memo.type, "Note")
                linked = f" ({memo.linked_key})" if memo.linked_key else ""
                content = (memo.content or "").strip().replace("\n", " ")
                if content:
                    annotation_sections.append(f"- {label}{linked}: {content}")
            annotation_sections.append("")

        annotations_block = "\n".join(annotation_sections)

        # Load completed participants
        all_completed = [p for p in project.participants if p.status == "completed" and p.turns]

        # Business + study context — same grounding as the v1 run.
        company = db.query(Company).filter(Company.id == project.company_id).first()
        context_block = full_context_block(company, project)

        objective_block = (
            f"RESEARCH OBJECTIVE:\n{project.research_objective}\n\n"
            if project.research_objective
            else ""
        )

        transcripts_block, _ = _build_transcripts_block(all_completed)

        # Same researcher-verified codebook evidence as the v1 run — by the
        # refine stage the researcher has usually tagged more, so this block
        # matters even more here.
        codebook_stats = _codebook_stats(db, project_id, all_completed)
        codebook_block = _build_codebook_block(codebook_stats)

        lang = getattr(company, "preferred_language", None) or "en"
        lang_instruction = _lang_instruction(lang)

        prompt = (
            f"{_ANALYSIS_RULES_BLOCK}\n\n"
            f"{_ANALYSIS_SCHEMA_BLOCK}\n\n"
            f"<task>\nThis is a REFINED synthesis (v2). A v1 was produced and the researcher "
            f"reviewed it. Their annotations and notes are below — treat them as expert "
            f"signals from someone who has read every transcript. Re-synthesize from the "
            f"transcripts, applying the annotations:\n"
            f"- CONFIRMED themes: keep, strengthen evidence, do not weaken.\n"
            f"- DISPUTED themes: re-examine. If you reframe, add a `researcher_note` field "
            f"to that theme object (1-2 sentences explaining what changed). If transcript "
            f"evidence still overwhelmingly supports the original framing, keep it AND add "
            f"`researcher_note` explaining the disagreement with the researcher.\n"
            f"- NEEDS-EVIDENCE themes: include ONLY if ≥2 quotes from ≥2 distinct participants "
            f"now support them. Otherwise drop.\n"
            f"In the `summary` field, add one sentence noting this is a researcher-refined synthesis.\n"
            f"All other rules (calibration to N={len(all_completed)}, ≥2 distinct participants per theme, "
            f"named participants in frequency, disconfirming evidence, object-shaped falsifiable "
            f"recommendations, personas grounded in ≥2 named participants, journey only when the "
            f"experience is temporal) still apply without exception.{lang_instruction}\n</task>\n\n"
            f"{context_block}{objective_block}{annotations_block}\n{codebook_block}"
            f"<transcripts count=\"{len(all_completed)}\">\n{transcripts_block}\n</transcripts>\n\n"
            f"Return the JSON object now. participant_count must be {len(all_completed)}."
        )

        # Refined synthesis is the researcher's high-stakes pass (they've reviewed
        # v1 and annotated) → run it at xhigh effort.
        _set_stage(db, new_analysis, "synthesizing")
        response = _synthesize_response(prompt, effort="xhigh")
        log_claude_usage(db, response, "analysis", company_id=project.company_id, project_id=project_id)
        _raise_on_bad_stop(response)

        _set_stage(db, new_analysis, "verifying")
        report_obj = _parse_report(response)
        v_count, v_total = _verify_report_quotes(report_obj, all_completed)
        if v_total:
            logger.info(
                "refined analysis quote verification: %d/%d verbatim (project=%s)",
                v_count, v_total, project_id,
            )

        if codebook_stats:
            report_obj["codebook_stats"] = [
                {k: v for k, v in s.items() if k != "quotes"} for s in codebook_stats
            ]

        new_analysis.report = json.dumps(report_obj)
        new_analysis.status = "ready"
        new_analysis.participant_count = len(all_completed)
        new_analysis.generated_at = datetime.utcnow()

    except Exception as e:
        new_analysis.status = "failed"
        new_analysis.error = str(e)

    new_analysis.stage = None
    new_analysis.stage_detail = None
    db.commit()
