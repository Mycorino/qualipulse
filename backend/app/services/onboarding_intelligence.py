"""Onboarding intelligence — Claude-powered study draft generation.

Single entry point: ``generate_onboarding_study`` turns the user's intake
(role, research intent, business context) into a ready-to-launch study
draft (brief summary + objective + audience + interview guide).

Follows the same resilience pattern as ``website_intelligence.py``: check
for an API key, call Claude with a tight timeout, parse JSON, and return
None on any failure so the caller can fall back gracefully.
"""

import json
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"

_LANGUAGE_NAMES = {"en": "English", "fr": "French"}


def generate_onboarding_study(
    first_name: Optional[str] = None,
    company_name: Optional[str] = None,
    role_title: Optional[str] = None,
    research_intent: Optional[str] = None,
    research_experience: Optional[str] = None,
    industry: Optional[str] = None,
    business_summary: Optional[str] = None,
    goals_freeform: Optional[str] = None,
    language: str = "en",
) -> Optional[dict]:
    """Generate a ready-to-use study draft from onboarding intake.

    Returns a dict with ``brief_summary``, ``study_title``, ``research_objective``,
    ``target_audience``, ``duration_minutes``, ``sample_size``, and ``questions``
    (a list of QuestionCreate-shaped dicts). Returns None on any failure — the
    caller should fall back to a "start from blank" path.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("onboarding_intelligence.study: no API key")
        return None

    language_name = _LANGUAGE_NAMES.get(language, "English")
    lang_instruction = (
        f"Write ALL user-facing strings (brief_summary, study_title, research_objective, "
        f"target_audience, section_title, main_question, interview_notes, desired_learning) "
        f"in {language_name}. JSON keys stay in English."
    )

    system_msg = (
        "You are a senior qualitative researcher designing a ready-to-launch voice "
        "interview study from a short intake. You write questions that ELICIT STORIES, "
        "not opinions. You refuse to write yes/no, leading, double-barrelled, or "
        "hypothetical questions. Output is parsed by code — return ONLY valid JSON."
    )

    prompt = (
        f"<intake>\n"
        f"Researcher: {first_name or 'the researcher'}\n"
        f"Role: {role_title or 'Not specified'}\n"
        f"Company: {company_name or 'Not specified'}\n"
        f"Industry: {industry or 'Not specified'}\n"
        f"Business context: {business_summary or 'Not specified'}\n"
        f"Research experience: {research_experience or 'Not specified'}\n"
        f"What they want to learn: {research_intent or 'Not specified'}\n"
        f"Additional notes: {goals_freeform or 'None'}\n"
        f"</intake>\n\n"
        f"<task>\n"
        f"Design a complete first study from this intake. Output a JSON object with:\n"
        f"- brief_summary: 2 short sentences (max 280 chars total) confirming what the "
        f"researcher wants to learn. Start with \"Based on what you told us\" or similar. "
        f"NEVER invent specific numbers, percentages, market sizes, or competitor names "
        f"the user didn't provide.\n"
        f"- study_title: a concrete study name (max 60 chars). Reference the actual topic, "
        f"not a generic phrase. GOOD: \"Why mid-market teams hesitate at checkout\". "
        f"BAD: \"Customer research study\".\n"
        f"- research_objective: ONE sentence describing what insight the study will surface. "
        f"Grounded in the user's stated intent.\n"
        f"- target_audience: 1-2 sentences describing who to interview. Be specific about "
        f"behavior or role, not demographics alone.\n"
        f"- key_insights: array of EXACTLY 3 specific findings this study will surface. "
        f"Each is one sentence (max 18 words) describing a CONCRETE insight a researcher "
        f"would actually use — not a topic, not a question. "
        f"GOOD: \"Which moments in the checkout flow trigger hesitation among first-time buyers\", "
        f"\"How architects discover technical references when working under tight design deadlines\". "
        f"BAD: \"Customer satisfaction\" (topic), \"Why do users churn?\" (question), "
        f"\"Lose 25% of revenue\" (invented number). "
        f"Each insight must feel like a sentence the user would screenshot to share with their team.\n"
        f"- why_this_matters: 1-2 sentences (max 280 chars total) explaining the strategic value "
        f"of running THIS study now. Reference the user's actual business / role / industry. "
        f"NEVER invent metrics, market sizes, percentages, or competitor names. Frame as opportunity "
        f"or risk, not as marketing copy. NEVER use words like \"unlock\", \"empower\", \"leverage\", "
        f"\"seamless\", \"game-changing\", \"transform\".\n"
        f"- duration_minutes: 15 or 20 (integer). Use 15 unless the topic genuinely needs more.\n"
        f"- sample_size: integer between 5 and 8. Recommend 6 by default.\n"
        f"- questions: array of exactly 5 question objects. Shape:\n"
        f"  {{\"section_index\": int, \"section_title\": str, \"question_index\": int, "
        f"\"main_question\": str, \"interview_notes\": str, \"desired_learning\": str}}\n"
        f"  Use 3 sections: warmup (1 question, builds rapport), core (3 questions, the "
        f"heart of the study), closing (1 question, reflective).\n"
        f"- other_directions: array of exactly 3 OTHER research questions this researcher "
        f"might want to run later, DIFFERENT from the main study above. Each is one short "
        f"sentence (max 12 words), phrased as a curiosity. Reference the actual business "
        f"context, not generic topics. NEVER invent specific numbers or metrics. "
        f"GOOD: \"How do new hires onboard onto the dashboard?\". "
        f"BAD: \"Customer feedback\" (too vague), \"Why did churn rise 12% in Q2\" (invented numbers).\n"
        f"</task>\n\n"
        f"<question_rules>\n"
        f"- Open-ended ONLY. NEVER yes/no.\n"
        f"- Single concept per question. NEVER double-barrelled.\n"
        f"- NON-LEADING. \"What was frustrating about X?\" is leading. "
        f"\"Walk me through the last time you used X\" is not.\n"
        f"- AVOID 'why'. Prefer \"walk me through\", \"tell me about the last time\", "
        f"\"what was happening when\", \"what led you to\".\n"
        f"- Past-tense story prompts beat hypothetical questions.\n"
        f"- interview_notes: 1-2 concrete probes the interviewer can fall back on. Not "
        f"repetition of the question.\n"
        f"- desired_learning: ONE sentence on what insight this surfaces.\n"
        f"</question_rules>\n\n"
        f"<output_format>\n"
        f"Return ONLY this JSON shape, no fences, no preamble:\n"
        f"{{\n"
        f'  "brief_summary": "...",\n'
        f'  "study_title": "...",\n'
        f'  "research_objective": "...",\n'
        f'  "target_audience": "...",\n'
        f'  "key_insights": ["...", "...", "..."],\n'
        f'  "why_this_matters": "...",\n'
        f'  "duration_minutes": 15,\n'
        f'  "sample_size": 6,\n'
        f'  "questions": [\n'
        f'    {{"section_index": 0, "section_title": "...", "question_index": 0, '
        f'"main_question": "...", "interview_notes": "...", "desired_learning": "..."}}\n'
        f"  ],\n"
        f'  "other_directions": ["...", "...", "..."]\n'
        f"}}\n"
        f"</output_format>\n\n"
        f"{lang_instruction}"
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=2048,
            temperature=0.4,
            timeout=25.0,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "") or ""

        text = text.strip()
        # Strip code fences if Claude added them despite instructions
        if text.startswith("```"):
            text = text.split("```", 2)[1] if "```" in text[3:] else text[3:]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)

        # Minimal validation — caller can still fall back on bad shape
        if not isinstance(parsed, dict):
            return None
        if "questions" not in parsed or not isinstance(parsed["questions"], list):
            return None
        if not parsed.get("study_title") or not parsed.get("research_objective"):
            return None

        # Coerce duration + sample size to safe ranges
        try:
            parsed["duration_minutes"] = max(10, min(60, int(parsed.get("duration_minutes", 15))))
        except (ValueError, TypeError):
            parsed["duration_minutes"] = 15
        try:
            parsed["sample_size"] = max(3, min(20, int(parsed.get("sample_size", 6))))
        except (ValueError, TypeError):
            parsed["sample_size"] = 6

        # other_directions is optional — coerce to a clean list of strings.
        # Surfaces alternative research questions on Step 4 + reused as
        # selected_use_cases in the welcome email so the 3 suggestions
        # there match what we showed in-app.
        raw_other = parsed.get("other_directions") or []
        if isinstance(raw_other, list):
            parsed["other_directions"] = [
                str(s).strip() for s in raw_other if isinstance(s, str) and s.strip()
            ][:3]
        else:
            parsed["other_directions"] = []

        # key_insights — the headline "what you'll learn" bullets on Step 4.
        # These are the conversion content, not the questions. Coerce to a
        # clean string list and trim to 3.
        raw_insights = parsed.get("key_insights") or []
        if isinstance(raw_insights, list):
            parsed["key_insights"] = [
                str(s).strip() for s in raw_insights if isinstance(s, str) and s.strip()
            ][:3]
        else:
            parsed["key_insights"] = []

        # why_this_matters — strategic framing sentence. Optional string.
        raw_why = parsed.get("why_this_matters")
        if isinstance(raw_why, str) and raw_why.strip():
            parsed["why_this_matters"] = raw_why.strip()
        else:
            parsed["why_this_matters"] = ""

        logger.info(
            "onboarding_intelligence.study: generated %d questions for %s",
            len(parsed["questions"]),
            first_name or "unknown",
        )
        return parsed

    except Exception as exc:
        logger.warning("onboarding_intelligence.study failed: %s", exc)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Research plan generation (onboarding Step 4 — the mixed-methods upgrade)
# ─────────────────────────────────────────────────────────────────────────────
#
# ``generate_research_plan`` supersedes ``generate_onboarding_study``. Instead
# of a single interview study, it returns a sequenced 3-phase research program
# (screener survey → in-depth interviews → validation survey) that mirrors what
# the product now does end-to-end: quantify → explain → validate.
#
# API design notes (see the claude-api skill):
#   * Model: Opus 4.7 — this is the onboarding conversion moment; plan quality
#     beats a few seconds of latency.
#   * Prompt caching: the methodology system prompt is frozen and identical for
#     every signup (EN or FR). It sits in a cache_control'd system block. The
#     language directive + per-user intake go in the user turn, so EN and FR
#     calls share one cached prefix.
#   * Structured output: output_config.format with a json_schema constrains
#     the response to valid, parseable JSON — no fence-stripping guesswork.
#     (JSON Schema can't express minItems/maxItems, so the "exactly 3 phases /
#     5 questions" cardinality is still enforced in the post-parse coercion.)

_PLAN_MODEL = "claude-opus-4-7"

# JSON schema for output_config.format — every object additionalProperties:
# false with all properties required, as structured outputs expects.
_RESEARCH_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "brief_summary": {"type": "string"},
        "plan_title": {"type": "string"},
        "timeline_estimate": {"type": "string"},
        "phases": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "number": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["survey", "interview"]},
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "what_it_answers": {"type": "string"},
                    "recommended_sample": {"type": "integer"},
                    "est_setup": {"type": "string"},
                },
                "required": [
                    "number", "kind", "title", "purpose",
                    "what_it_answers", "recommended_sample", "est_setup",
                ],
            },
        },
        "interview_guide": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "section_index": {"type": "integer"},
                    "section_title": {"type": "string"},
                    "question_index": {"type": "integer"},
                    "main_question": {"type": "string"},
                    "interview_notes": {"type": "string"},
                    "desired_learning": {"type": "string"},
                },
                "required": [
                    "section_index", "section_title", "question_index",
                    "main_question", "interview_notes", "desired_learning",
                ],
            },
        },
    },
    "required": [
        "brief_summary", "plan_title", "timeline_estimate",
        "phases", "interview_guide",
    ],
}

# Frozen methodology system prompt. Identical across every signup → cacheable.
# Encodes a quant→qual→quant triangulation design with real research rigour.
# Keep this BYTE-STABLE: any edit invalidates the prompt cache for all callers.
_RESEARCH_PLAN_SYSTEM = """You are the lead research strategist at QualiPulse, an AI-driven \
mixed-methods research platform. After an intake conversation with a new customer you \
design their first research program: a sequenced, methodologically sound plan they could \
hand to a research agency and have respected.

QualiPulse runs three instrument types, and a strong first program uses all three in \
sequence — a quant → qual → quant triangulation design:

  PHASE 1 — SCREENER SURVEY (quant, broad).
    A short survey to a wide audience that does two jobs at once:
      (a) sizes the phenomenon — gives a directional read on how widespread it is;
      (b) recruits — identifies the specific sub-population worth interviewing.
    It MUST include at least one behavioural or attitudinal segmentation question,
    not demographics alone. Recommended sample: 150–250 respondents (enough to
    surface the qualified segment and read any single percentage at n ≥ 30).

  PHASE 2 — IN-DEPTH INTERVIEWS (qual, deep).
    Voice interviews with the segment that EMERGED from Phase 1 data — not a
    pre-guessed audience. This phase answers the "why" the survey can't.
    Sample size is governed by thematic saturation: 8–12 interviews, default 10.

  PHASE 3 — VALIDATION SURVEY (quant, confirmatory).
    Takes the themes discovered in Phase 2 and tests them at scale, on an
    audience filtered by the criteria Phase 2 revealed. One agree/disagree
    item per theme. Recommended sample: 100+ respondents.

NON-NEGOTIABLE METHODOLOGY RULES:
  * Each phase's OUTPUT explicitly feeds the NEXT phase's design. Phase 2's
    audience comes from Phase 1; Phase 3's items come from Phase 2. Say so.
  * Never report or imply a percentage on a base smaller than n = 30.
  * Never claim causation from correlation. A survey shows association; only
    the interviews can surface mechanism.
  * Screener questions describe ACTUAL past behaviour, never hypotheticals.
  * Interview questions ELICIT STORIES, not opinions: open-ended only, one
    concept per question, non-leading, past-tense ("walk me through the last
    time…"), and they avoid the word "why".
  * Sample sizes and the timeline are a RECOMMENDED DESIGN the user can edit —
    present them as such, never as a guarantee or an SLA.

HARD ANTI-HALLUCINATION RULE:
  Never invent a number, percentage, market size, growth rate, competitor name,
  customer segment, or business problem that the user did not provide. Ground
  every sentence in the intake. If the intake is thin, stay general — do not
  fabricate specificity.

VOICE: a senior consultant who listened. Concise, concrete, no marketing-speak.
BANNED words: unlock, empower, leverage, seamless, game-changing, transform,
revolutionise, supercharge. No exclamation marks. No emojis.

Your output is parsed by code — return only the JSON object, no preamble, no fences."""


def generate_research_plan(
    first_name: Optional[str] = None,
    company_name: Optional[str] = None,
    role_title: Optional[str] = None,
    research_intent: Optional[str] = None,
    research_experience: Optional[str] = None,
    industry: Optional[str] = None,
    business_summary: Optional[str] = None,
    goals_freeform: Optional[str] = None,
    language: str = "en",
) -> Optional[dict]:
    """Generate a sequenced 3-phase research plan from onboarding intake.

    Returns a dict with ``brief_summary``, ``plan_title``, ``timeline_estimate``,
    ``phases`` (exactly 3: screener survey → interviews → validation survey) and
    ``interview_guide`` (5 QuestionCreate-shaped dicts for the Phase-2 project).
    Returns None on any failure — the caller falls back to "start from blank".
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("onboarding_intelligence.plan: no API key")
        return None

    language_name = _LANGUAGE_NAMES.get(language, "English")

    # Volatile content (language directive + intake) goes in the user turn so
    # the cached system prefix is identical for every signup, EN or FR.
    user_prompt = (
        f"Write every user-facing string in {language_name}. JSON keys stay in English.\n\n"
        f"<intake>\n"
        f"Researcher: {first_name or 'the researcher'}\n"
        f"Role: {role_title or 'Not specified'}\n"
        f"Company: {company_name or 'Not specified'}\n"
        f"Industry: {industry or 'Not specified'}\n"
        f"Business context: {business_summary or 'Not specified'}\n"
        f"Research experience: {research_experience or 'Not specified'}\n"
        f"What they want to learn: {research_intent or 'Not specified'}\n"
        f"Additional notes: {goals_freeform or 'None'}\n"
        f"</intake>\n\n"
        f"<task>\n"
        f"Design this customer's first research program. Produce a JSON object:\n"
        f"- brief_summary: 2 sentences (max 300 chars) confirming what they want to "
        f"learn. Open with \"Based on what you told us\" or the {language_name} equivalent.\n"
        f"- plan_title: a concrete name for the overall program (max 70 chars).\n"
        f"- timeline_estimate: a SHORT phrase, framed as a projection not a promise "
        f"(e.g. the {language_name} equivalent of \"first results in about a week\").\n"
        f"- phases: EXACTLY 3 objects, in order:\n"
        f"    1. kind=\"survey\"    — the screener survey (Phase 1 above)\n"
        f"    2. kind=\"interview\" — the in-depth interviews (Phase 2 above)\n"
        f"    3. kind=\"survey\"    — the validation survey (Phase 3 above)\n"
        f"  Each phase: number (1/2/3), kind, title (max 60 chars), purpose "
        f"(1 sentence), what_it_answers (1 sentence — the concrete question this "
        f"phase resolves), recommended_sample (integer), est_setup (a short phrase "
        f"like the {language_name} for \"live in 10 minutes\" for phase 1, or "
        f"\"~10 interviews\" / \"~1 day to field\" for the others).\n"
        f"- interview_guide: EXACTLY 5 questions for the Phase-2 interviews. Shape: "
        f"{{section_index, section_title, question_index, main_question, "
        f"interview_notes, desired_learning}}. Three sections — a 1-question warm-up, "
        f"a 3-question core, a 1-question reflective close. Story-elicitation, "
        f"past-tense, non-leading, one concept each.\n"
        f"</task>\n\n"
        f"<output_format>\n"
        f"Return ONLY this JSON shape, no fences, no preamble:\n"
        f"{{\n"
        f'  "brief_summary": "...",\n'
        f'  "plan_title": "...",\n'
        f'  "timeline_estimate": "...",\n'
        f'  "phases": [\n'
        f'    {{"number": 1, "kind": "survey", "title": "...", "purpose": "...", '
        f'"what_it_answers": "...", "recommended_sample": 200, "est_setup": "..."}},\n'
        f'    {{"number": 2, "kind": "interview", "title": "...", "purpose": "...", '
        f'"what_it_answers": "...", "recommended_sample": 10, "est_setup": "..."}},\n'
        f'    {{"number": 3, "kind": "survey", "title": "...", "purpose": "...", '
        f'"what_it_answers": "...", "recommended_sample": 100, "est_setup": "..."}}\n'
        f"  ],\n"
        f'  "interview_guide": [\n'
        f'    {{"section_index": 0, "section_title": "...", "question_index": 0, '
        f'"main_question": "...", "interview_notes": "...", "desired_learning": "..."}}\n'
        f"  ]\n"
        f"}}\n"
        f"</output_format>"
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        # Prompt caching: the methodology system prompt is a cache_control'd
        # block — frozen and identical across every signup, so it is written
        # once and read on subsequent calls within the TTL.
        # Structured output: output_config.format constrains the response to
        # the schema, so the text block is guaranteed valid JSON.
        response = client.with_options(timeout=60.0).messages.create(
            model=_PLAN_MODEL,
            max_tokens=8000,
            system=[
                {
                    "type": "text",
                    "text": _RESEARCH_PLAN_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": _RESEARCH_PLAN_SCHEMA,
                }
            },
            messages=[{"role": "user", "content": user_prompt}],
        )

        text = ""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "") or ""

        # output_config.format guarantees valid JSON — but keep a defensive
        # fence-strip in case a refusal or edge case slips through.
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1] if "```" in text[3:] else text[3:]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        parsed = json.loads(text)

        if not isinstance(parsed, dict):
            return None
        phases = parsed.get("phases")
        guide = parsed.get("interview_guide")
        if not isinstance(phases, list) or len(phases) != 3:
            return None
        if not isinstance(guide, list) or not guide:
            return None
        if not parsed.get("plan_title") or not parsed.get("brief_summary"):
            return None

        # Coerce each phase's recommended_sample into a sane range so a bad
        # model number never reaches the UI as a quota.
        for phase in phases:
            try:
                phase["recommended_sample"] = max(
                    5, min(1000, int(phase.get("recommended_sample", 100)))
                )
            except (ValueError, TypeError):
                phase["recommended_sample"] = 100

        usage = getattr(response, "usage", None)
        logger.info(
            "onboarding_intelligence.plan: 3-phase plan for %s "
            "(cache_read=%s, cache_write=%s)",
            first_name or "unknown",
            getattr(usage, "cache_read_input_tokens", None),
            getattr(usage, "cache_creation_input_tokens", None),
        )
        return parsed

    except Exception as exc:
        logger.warning("onboarding_intelligence.plan failed: %s", exc)
        return None
