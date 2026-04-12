"""Generate a personalised welcome email body using Claude.

Called after onboarding completes — the email includes three concrete study
ideas tailored to the user's role and occupation. Falls back to the generic
welcome email if anything goes wrong.
"""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 1024

_LANGUAGE_NAMES = {"en": "English", "fr": "French"}


def generate_personalized_welcome(
    first_name: Optional[str] = None,
    last_name: Optional[str] = None,
    company_name: Optional[str] = None,
    role_title: Optional[str] = None,
    occupation_description: Optional[str] = None,
    industry: Optional[str] = None,
    selected_use_cases: Optional[list[str]] = None,
    language: str = "en",
) -> Optional[str]:
    """Generate a personalised welcome email body (HTML).

    Returns an HTML string suitable for embedding inside our email wrapper,
    or None on any failure.
    """
    if not settings.ANTHROPIC_API_KEY:
        logger.warning("welcome_email_generator: no API key")
        return None

    language_name = _LANGUAGE_NAMES.get(language, "English")
    use_cases_str = ", ".join(selected_use_cases) if selected_use_cases else "Not specified"

    prompt = (
        "<system>\n"
        "Write a follow-up email after an onboarding session for QualiPulse, "
        "an AI qualitative interview platform. Write like a consultant, not a "
        "marketer.\n"
        "</system>\n\n"
        "<context>\n"
        f"Recipient: {first_name or ''} {last_name or ''} "
        f"({role_title or 'Researcher'}) at {company_name or 'their company'}\n"
        f"Focus: {occupation_description or 'Not specified'}\n"
        f"Industry: {industry or 'Not specified'}\n"
        f"Research interests: {use_cases_str}\n"
        "</context>\n\n"
        "<instructions>\n"
        f"Write in {language_name}. Structure:\n"
        f"1. Greet {first_name or 'the user'} by name\n"
        "2. One sentence about their role/context\n"
        '3. "Based on your profile, here are three studies you could launch '
        'this week:" -- 3 specific research questions for their occupation\n'
        "4. Point to demo project in dashboard\n"
        '5. Sign off from "The QualiPulse team"\n\n'
        "Under 150 words. HTML (<p>, <ul>/<li>). No markdown, no emojis.\n"
        "</instructions>"
    )

    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
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
            "welcome_email_generator: generated %d chars for %s",
            len(text),
            first_name or "unknown",
        )
        return text

    except Exception as exc:
        logger.warning("welcome_email_generator failed: %s", exc)
        return None
