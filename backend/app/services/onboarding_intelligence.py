"""Onboarding intelligence — role classification + recap generation.

Two Claude-powered helpers used during the redesigned onboarding flow:

1. ``classify_role_and_suggest`` — maps a free-form role description into a
   canonical tag + orientation and generates personalised use-case suggestions.
2. ``generate_onboarding_recap`` — writes a short strategy-brief recap that
   makes the user feel understood before they hit the dashboard.

Both follow the same resilience pattern as ``website_intelligence.py``:
check for an API key, call Claude with a tight timeout, parse JSON from the
response, and return a safe fallback (or None) on any failure.
"""

import json
import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 1024

_LANGUAGE_NAMES = {"en": "English", "fr": "French"}

_FALLBACK_CLASSIFY = {
    "canonical_tag": "general",
    "orientation": "mixed",
    "suggested_use_cases": [
        "Why do users drop off before completing signup?",
        "What frustrations drive customers to competitors?",
        "How do users decide which features matter most?",
        "What unmet needs do our best customers have?",
        "Why do trial users not convert to paid?",
    ],
    "research_angle": "Understanding your users and market through qualitative interviews.",
}


def classify_role_and_suggest(
    role_title: Optional[str] = None,
    occupation_description: Optional[str] = None,
    industry: Optional[str] = None,
    business_summary: Optional[str] = None,
    language: str = "en",
) -> dict:
    """Classify a professional role and suggest personalised research topics.

    Returns a dict with keys: canonical_tag, orientation, suggested_use_cases,
    research_angle. On any failure returns a safe fallback dict.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("onboarding_intelligence.classify: no API key")
        return dict(_FALLBACK_CLASSIFY)

    language_name = _LANGUAGE_NAMES.get(language, "English")

    system_msg = (
        "You are a strict role classifier and research-topic suggester for a qualitative "
        "research SaaS. Output is parsed by code — return ONLY valid JSON."
    )

    prompt = (
        f"<input>\n"
        f"Role title: {role_title or 'Not specified'}\n"
        f"Day-to-day focus: {occupation_description or 'Not specified'}\n"
        f"Industry: {industry or 'Not specified'}\n"
        f"Company: {business_summary or 'Not specified'}\n"
        f"</input>\n\n"
        f"<canonical_tags>\n"
        f"product_analytics, product_management, brand_marketing, growth_marketing, "
        f"ux_research, design, customer_success, hr_operations, founder, consultant, "
        f"academic, sales, general\n"
        f"</canonical_tags>\n\n"
        f"<rules>\n"
        f"- canonical_tag: pick the closest from the list above. Use \"general\" only when "
        f"no other clearly fits.\n"
        f"- orientation: \"internal\" (product/ops/HR/employees), \"external\" "
        f"(marketing/brand/sales/customers), or \"mixed\".\n"
        f"- suggested_use_cases: exactly 5 short research questions (max 12 words each). "
        f"Each must be a concrete question this person would care about, phrased as a "
        f"curiosity they can explore through interviews. "
        f"NEVER invent specific numbers, percentages, timeframes, or metrics you don't know. "
        f"GOOD: \"Why do customers drop off during checkout?\", \"What competitors are users switching to?\". "
        f"BAD: \"Why are EMEA conversion rates 3% lower than NA\" (you don't know real numbers). "
        f"BAD: \"Customer feedback\", \"User research\" (too vague, not a question). "
        f"Write in {language_name}.\n"
        f"- research_angle: ONE sentence describing what kind of insight this person actually "
        f"needs (not what they could do, but what blocks them). Write in {language_name}.\n"
        f"</rules>\n\n"
        f"<output_format>\n"
        f"Return ONLY this JSON shape, no fences, no preamble:\n"
        f"{{\n"
        f'  "canonical_tag": "...",\n'
        f'  "orientation": "internal" | "external" | "mixed",\n'
        f'  "suggested_use_cases": ["...", "..."],\n'
        f'  "research_angle": "..."\n'
        f"}}\n"
        f"</output_format>"
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.3,
            timeout=10.0,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "") or ""

        text = text.strip()
        # Strip markdown fences
        if text.startswith("```"):
            import re
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)

        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Response is not a JSON object")

        # Validate expected keys
        result = {
            "canonical_tag": str(payload.get("canonical_tag", "general")),
            "orientation": str(payload.get("orientation", "mixed")),
            "suggested_use_cases": payload.get("suggested_use_cases", []),
            "research_angle": str(payload.get("research_angle", "")),
        }
        if not isinstance(result["suggested_use_cases"], list):
            result["suggested_use_cases"] = []

        logger.info(
            "onboarding_intelligence.classify: tag=%s orientation=%s",
            result["canonical_tag"],
            result["orientation"],
        )
        return result

    except Exception as exc:
        logger.warning("onboarding_intelligence.classify failed: %s", exc)
        return dict(_FALLBACK_CLASSIFY)


def generate_onboarding_recap(
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    company_name: Optional[str] = None,
    role_title: Optional[str] = None,
    occupation_description: Optional[str] = None,
    research_experience: Optional[str] = None,
    industry: Optional[str] = None,
    business_summary: Optional[str] = None,
    selected_use_cases: Optional[list[str]] = None,
    goals_freeform: Optional[str] = None,
    language: str = "en",
) -> Optional[str]:
    """Generate a personalised research-needs recap for the onboarding outro.

    Returns the recap as a plain-text string, or None on any failure.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("onboarding_intelligence.recap: no API key")
        return None

    language_name = _LANGUAGE_NAMES.get(language, "English")
    use_cases_str = ", ".join(selected_use_cases) if selected_use_cases else "Not specified"

    system_msg = (
        "You are a senior research strategist writing the opening of a strategy brief after "
        "an intake call. Voice: a human consultant who listened — concise, warm, specific, "
        "no marketing-speak."
    )

    prompt = (
        f"<intake_notes>\n"
        f"Client: {first_name or ''} {last_name or ''}\n"
        f"Role: {role_title or 'Not specified'}\n"
        f"Day-to-day focus: {occupation_description or 'Not specified'}\n"
        f"Company: {company_name or 'Not specified'}\n"
        f"Industry: {industry or 'Not specified'}\n"
        f"Research experience: {research_experience or 'Not specified'}\n"
        f"Business context: {business_summary or 'Not specified'}\n"
        f"Stated priorities: {use_cases_str}\n"
        f"Additional notes: {goals_freeform or 'None'}\n"
        f"</intake_notes>\n\n"
        f"<task>\n"
        f"Write a personalised research-needs recap in {language_name}. Frame everything "
        f"around the client's ACTUAL DAY-TO-DAY FOCUS (their own words), not their job title.\n\n"
        f"Structure (light markdown):\n"
        f"1. Opening paragraph (2-3 sentences) addressing **{first_name or 'the client'}** "
        f"and **{company_name or 'their company'}**. Bold 1-2 phrases from their intake "
        f"that prove you listened.\n"
        f"2. 3-4 bullet points (`- ` markdown bullets). Each bullet is ONE specific research "
        f"question they probably face, connected to a business outcome. Bold the core "
        f"question within each bullet.\n"
        f"3. Closing paragraph: how AI-driven interviews fit their specific workflow — "
        f"reference something concrete from intake, not the platform's generic value prop.\n"
        f"</task>\n\n"
        f"<rules>\n"
        f"- Under 180 words.\n"
        f"- BANNED vocabulary: \"unlock\", \"empower\", \"leverage\", \"seamless\", "
        f"\"game-changing\", \"delight\", \"journey\", \"unleash\", \"drive engagement\".\n"
        f"- No exclamation marks. No emojis. No headers. No code blocks.\n"
        f"- Use **bold** and `- ` only. No other markdown.\n"
        f"- Specificity test: each bullet question should be one a colleague could literally "
        f"start tomorrow. \"Why mid-market churns at month 4\" — good. \"Understand customer "
        f"needs\" — REJECT.\n"
        f"</rules>\n\n"
        f"Write in {language_name}. Return only the recap text."
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.7,
            timeout=15.0,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
        )

        text = ""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "") or ""

        text = text.strip()
        if not text:
            return None

        logger.info(
            "onboarding_intelligence.recap: generated %d chars for %s",
            len(text),
            first_name or "unknown",
        )
        return text

    except Exception as exc:
        logger.warning("onboarding_intelligence.recap failed: %s", exc)
        return None


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
        f"- duration_minutes: 15 or 20 (integer). Use 15 unless the topic genuinely needs more.\n"
        f"- sample_size: integer between 5 and 8. Recommend 6 by default.\n"
        f"- questions: array of exactly 5 question objects. Shape:\n"
        f"  {{\"section_index\": int, \"section_title\": str, \"question_index\": int, "
        f"\"main_question\": str, \"interview_notes\": str, \"desired_learning\": str}}\n"
        f"  Use 3 sections: warmup (1 question, builds rapport), core (3 questions, the "
        f"heart of the study), closing (1 question, reflective).\n"
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
        f'  "duration_minutes": 15,\n'
        f'  "sample_size": 6,\n'
        f'  "questions": [\n'
        f'    {{"section_index": 0, "section_title": "...", "question_index": 0, '
        f'"main_question": "...", "interview_notes": "...", "desired_learning": "..."}}\n'
        f"  ]\n"
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

        logger.info(
            "onboarding_intelligence.study: generated %d questions for %s",
            len(parsed["questions"]),
            first_name or "unknown",
        )
        return parsed

    except Exception as exc:
        logger.warning("onboarding_intelligence.study failed: %s", exc)
        return None
