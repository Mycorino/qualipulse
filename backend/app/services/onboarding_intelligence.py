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

        logger.info(
            "onboarding_intelligence.study: generated %d questions for %s",
            len(parsed["questions"]),
            first_name or "unknown",
        )
        return parsed

    except Exception as exc:
        logger.warning("onboarding_intelligence.study failed: %s", exc)
        return None
