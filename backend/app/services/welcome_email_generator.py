"""Generate a personalised welcome email body using Claude.

Called after onboarding completes — the email includes three concrete study
ideas tailored to the user's role and occupation. Falls back to the generic
welcome email if anything goes wrong.
"""

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
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

    system_msg = (
        "You write the follow-up email after an onboarding intake for QualiPulse, an AI "
        "qualitative interview platform. Voice: senior research consultant who has actually "
        "read the intake notes — concise, specific, no marketing-speak. The reader is a busy "
        "professional; one wasted line and they bounce."
    )

    prompt = (
        f"<recipient>\n"
        f"Name: {first_name or ''} {last_name or ''}\n"
        f"Role: {role_title or 'Researcher'} at {company_name or 'their company'}\n"
        f"Day-to-day focus: {occupation_description or 'Not specified'}\n"
        f"Industry: {industry or 'Not specified'}\n"
        f"Stated research interests: {use_cases_str}\n"
        f"</recipient>\n\n"
        f"<task>\n"
        f"Write a personalised follow-up email body in {language_name}.\n\n"
        f"Structure:\n"
        f"1. Open with first name only — no \"Dear\".\n"
        f"2. One sentence that proves you read their intake (reference their actual focus, "
        f"not their job title).\n"
        f"3. \"Based on your profile, here are three studies you could launch this week:\" "
        f"followed by a <ul> with 3 items. Each item is ONE specific research question tied "
        f"to their stated use case — not a generic topic.\n"
        f"4. One short sentence pointing them to the demo project already in their dashboard.\n"
        f"5. Sign-off from \"The QualiPulse team\".\n"
        f"</task>\n\n"
        f"<rules>\n"
        f"- Under 150 words total.\n"
        f"- HTML only: <p>, <ul>, <li>. No <h*>, no inline styles, no markdown, no emojis.\n"
        f"- No marketing vocabulary: BANNED — \"unlock\", \"empower\", \"leverage\", "
        f"\"seamless\", \"game-changing\", \"delight\", \"journey\", \"unleash\".\n"
        f"- No exclamation marks.\n"
        f"- Each study question must be specific enough that a researcher could literally "
        f"run it tomorrow. \"Why power users plateau after 3 months\" — good. "
        f"\"Understand user behaviour\" — REJECT.\n"
        f"</rules>\n\n"
        f"Return ONLY the HTML body — no <html>/<body> wrapper, no preamble."
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
            "welcome_email_generator: generated %d chars for %s",
            len(text),
            first_name or "unknown",
        )
        return text

    except Exception as exc:
        logger.warning("welcome_email_generator failed: %s", exc)
        return None
