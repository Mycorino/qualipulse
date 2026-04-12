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
        "User discovery",
        "Customer feedback",
        "Product validation",
        "Market research",
        "Competitor analysis",
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

    prompt = (
        "<system>\n"
        "You are an expert at understanding professional roles and matching "
        "them to qualitative research needs.\n"
        "</system>\n\n"
        "<context>\n"
        f"Role title: {role_title or 'Not specified'}\n"
        f"What they focus on: {occupation_description or 'Not specified'}\n"
        f"Industry: {industry or 'Not specified'}\n"
        f"Company context: {business_summary or 'Not specified'}\n"
        "</context>\n\n"
        "<instructions>\n"
        "Return a JSON object with:\n"
        '1. "canonical_tag": short internal label (e.g. "product_analytics", '
        '"brand_marketing", "ux_research", "hr_operations", "founder", '
        '"consultant", "academic")\n'
        '2. "orientation": "internal" (product/ops/HR), "external" '
        '(marketing/brand/sales), or "mixed"\n'
        '3. "suggested_use_cases": 5-7 concrete research topics this SPECIFIC '
        "person would find relevant. Not generic like \"User research\" -- "
        'specific like "Why power users plateau after 3 months". '
        f"Write in {language_name}.\n"
        '4. "research_angle": One sentence describing what insights this '
        f"person needs. Write in {language_name}.\n\n"
        "Return valid JSON only.\n"
        "</instructions>"
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.3,
            timeout=10.0,
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

    prompt = (
        "<system>\n"
        "You are a senior research strategist at a top-tier qualitative "
        "research consultancy. Write the opening of a strategy brief after "
        "an intake meeting.\n"
        "</system>\n\n"
        "<context>\n"
        f"Client: {first_name or ''} {last_name or ''}\n"
        f"Role: {role_title or 'Not specified'}\n"
        f"Day-to-day focus: {occupation_description or 'Not specified'}\n"
        f"Company: {company_name or 'Not specified'}\n"
        f"Industry: {industry or 'Not specified'}\n"
        f"Research experience: {research_experience or 'Not specified'}\n"
        f"Business context: {business_summary or 'Not specified'}\n"
        f"Research priorities: {use_cases_str}\n"
        f"Additional notes: {goals_freeform or 'None'}\n"
        "</context>\n\n"
        "<instructions>\n"
        f"Write a personalized research needs assessment in {language_name}.\n\n"
        "Use the client's ACTUAL OCCUPATION to frame everything -- their own "
        "words about what they do, not a generic title.\n\n"
        "Structure (use light markdown formatting):\n"
        f"1. Opening paragraph (2-3 sentences) addressing **{first_name or 'the client'}** and "
        f"**{company_name or 'their company'}**, showing you understand their context. "
        "Use **bold** for key phrases that show you listened.\n"
        '2. A section with 3-4 bullet points (use `- ` markdown bullets), each a '
        "specific research question they probably face, connected to a business "
        "outcome. Bold the core question within each bullet.\n"
        "3. Closing paragraph about how AI-driven interviews fit their specific workflow.\n\n"
        "Under 180 words. Professional, warm. No exclamation marks, no emojis. "
        "Use **bold** for emphasis and `- ` for bullets. No headers, no code blocks. "
        f"Write in {language_name}.\n"
        "</instructions>"
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            temperature=0.7,
            timeout=15.0,
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
