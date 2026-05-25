"""Haiku-powered personalisation helpers for the /welcome surface.

Two cached generations, both keyed off the Company's wizard-captured
profile + business summary:

  - ``generate_welcome_greeting`` — a 3-paragraph greeting in the
    user's preferred language that quotes one concrete detail from
    their business summary, plants a value beat, and asks the
    opening question.

  - ``generate_starter_suggestions`` — three industry-aware "starter"
    research goals shown as chips under the canned greeting. Each is
    a 5-10 word casual question the user might type, NOT a study
    title.

Both cache for 24h on the Company row. Fail silent — callers receive
``None`` and fall back to static i18n strings.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import anthropic
import httpx

from app.config import settings
from app.models.company import Company

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5"
_CACHE_TTL = timedelta(hours=24)


def _is_fresh(stamp: datetime | None) -> bool:
    if stamp is None:
        return False
    return (datetime.utcnow() - stamp) < _CACHE_TTL


def _wizard_complete(company: Company) -> bool:
    """We only call Haiku once the wizard has captured the minimum we need
    to produce a meaningfully personalised output. A sparse prompt yields
    something worse than the static fallback, so we skip it."""
    return bool(
        (company.role or "").strip()
        and (company.company_size or "").strip()
        and (company.use_case or "").strip()
        and (company.business_summary or "").strip()
    )


def _lang(company: Company) -> str:
    return (company.preferred_language or "en").lower()


def generate_welcome_greeting(
    company: Company, *, force: bool = False
) -> Optional[str]:
    """Return a cached or freshly generated greeting string. None if we
    can't generate (sparse profile, API failure). Caller is responsible
    for committing the Company row when this returns a fresh string."""
    if not _wizard_complete(company):
        return None

    if not force and _is_fresh(company.welcome_greeting_at):
        cached = (company.welcome_greeting_text or "").strip()
        if cached:
            return cached

    if not settings.ANTHROPIC_API_KEY:
        return None

    role = (company.role or "").strip()
    first_name = (company.first_name or company.name or "there").strip()
    company_name = (company.name or "").strip()
    industry = (company.industry or "").strip()
    size = (company.company_size or "").strip()
    use_case = (company.use_case or "").strip()
    summary = (company.business_summary or "").strip()[:400]
    lang = _lang(company)
    lang_label = "French" if lang == "fr" else "English"

    system = (
        "You are the Research Copilot, greeting a new user for the first "
        "time on the QualiPulse onboarding screen. The user has just "
        "completed a 3-step structured wizard, so you already know their "
        "profile. Write a warm, factual 3-paragraph greeting.\n\n"
        f"WRITE IN {lang_label.upper()} ONLY. No language mixing.\n\n"
        "Paragraph 1 (1-2 lines): Greet them warmly. Reference ONE "
        "concrete specific detail from the business summary — a service "
        "they operate, a market they serve, a number they mention. NOT "
        "a generic platitude like 'exciting industry' or 'great market'.\n"
        "Paragraph 2 (1-2 lines): One short value beat connecting their "
        "use case to what voice interviews surface ('most teams would "
        "send a survey here — voice interviews reach the why, not the "
        "what'). Adapt to their actual world; do NOT recite this verbatim.\n"
        "Paragraph 3 (1 line): One sharp opening question that primes "
        "them to share their concrete research goal. Match their use_case "
        "(e.g. for product discovery: 'Quelle décision repose sur cette "
        "recherche ?' / 'What decision does this research need to "
        "inform?').\n\n"
        "Constraints: warm but not saccharine. No emoji. No bullet "
        "lists. No 'I'm thrilled' or 'exciting'. No talking about "
        "yourself — talk about THEIR situation. 200-300 characters total."
    )

    user = (
        f"First name: {first_name}\n"
        f"Company: {company_name}\n"
        f"Industry: {industry}\n"
        f"Role: {role}\n"
        f"Team size: {size}\n"
        f"Use case: {use_case}\n"
        f"Business summary: {summary}"
    )

    try:
        client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=httpx.Timeout(15.0),
        )
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=400,
            temperature=0.4,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text.strip()
        if not text:
            return None
        company.welcome_greeting_text = text
        company.welcome_greeting_at = datetime.utcnow()
        return text
    except Exception:  # noqa: BLE001 — silent fallback to static greeting
        logger.exception("Welcome greeting Haiku call failed")
        return None


def generate_starter_suggestions(
    company: Company, *, force: bool = False
) -> Optional[list[str]]:
    """Return a cached or freshly generated list of 3 starter-question
    strings. None if we can't generate."""
    if not _wizard_complete(company):
        return None

    if not force and _is_fresh(company.starter_suggestions_at):
        cached = (company.starter_suggestions_json or "").strip()
        if cached:
            try:
                arr = json.loads(cached)
                if isinstance(arr, list) and len(arr) == 3:
                    return [str(x).strip() for x in arr]
            except json.JSONDecodeError:
                pass  # fall through and regenerate

    if not settings.ANTHROPIC_API_KEY:
        return None

    role = (company.role or "").strip()
    company_name = (company.name or "").strip()
    industry = (company.industry or "").strip()
    use_case = (company.use_case or "").strip()
    summary = (company.business_summary or "").strip()[:400]
    lang = _lang(company)
    lang_label = "French" if lang == "fr" else "English"

    system = (
        "Generate three concrete research starter questions a "
        f"{role} at {company_name} ({industry}) might want to launch, "
        f"with their stated goal being '{use_case}'.\n\n"
        f"OUTPUT IN {lang_label.upper()} ONLY.\n\n"
        "Constraints:\n"
        "- Each starter is a question the user might TYPE into a "
        "research-tool prompt, NOT a study title. 5-10 words. Casual "
        "register (no 'How might we…' formality).\n"
        "- Use what the business ACTUALLY does (from the summary), not "
        "generic SaaS clichés like 'why trial users churn'.\n"
        "- Vary the angles: one about an existing problem, one about a "
        "new opportunity, one about a comparison or decision.\n"
        "- Return ONLY a JSON object with exact shape: "
        '{"suggestions": ["...", "...", "..."]}\n'
        "- No prose around it. No markdown fences."
    )

    user = (
        f"Business: {summary}\n"
        f"Audience the company serves: visible in summary\n"
        f"Researcher's framed goal: {use_case}"
    )

    try:
        client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=httpx.Timeout(15.0),
        )
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=300,
            temperature=0.6,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()
        parsed = json.loads(raw)
        arr = parsed.get("suggestions", [])
        if not isinstance(arr, list) or len(arr) != 3:
            return None
        cleaned = [str(x).strip() for x in arr if str(x).strip()]
        if len(cleaned) != 3:
            return None
        company.starter_suggestions_json = json.dumps(cleaned, ensure_ascii=False)
        company.starter_suggestions_at = datetime.utcnow()
        return cleaned
    except Exception:  # noqa: BLE001 — silent fallback to static chips
        logger.exception("Starter suggestions Haiku call failed")
        return None


def generate_demo_opening_question(
    company: Company, *, force: bool = False
) -> Optional[str]:
    """Return a cached or freshly generated participant-demo opening
    question. None if we can't generate. Caller commits the session.

    The demo modal asks the user one question and records their answer
    to show what the participant experience feels like. Without
    personalisation it's a generic "tell me about onboarding" which
    feels disconnected; this version produces a question that opens
    LIKE TURN 2 of a conversation — referencing the researcher's
    captured context so the demo lands like a real follow-up rather
    than a cold prompt."""
    if not _wizard_complete(company):
        return None

    if not force and _is_fresh(company.demo_opening_question_at):
        cached = (company.demo_opening_question_text or "").strip()
        if cached:
            return cached

    if not settings.ANTHROPIC_API_KEY:
        return None

    first_name = (company.first_name or company.name or "there").strip()
    role = (company.role or "").strip()
    company_name = (company.name or "").strip()
    industry = (company.industry or "").strip()
    use_case = (company.use_case or "").strip()
    summary = (company.business_summary or "").strip()[:400]
    lang = _lang(company)
    lang_label = "French" if lang == "fr" else "English"

    system = (
        f"You are the Research Copilot demonstrating the participant "
        f"interview experience to {first_name} — a {role} at "
        f"{company_name} ({industry}), focused on {use_case}.\n\n"
        f"Business context: {summary}\n\n"
        "Write a single follow-up question that sounds like TURN 2 "
        "of a real research conversation — the kind of question a "
        "researcher would ASK their participants if they were running "
        "THIS researcher's study. Open with a brief acknowledgement "
        "(\"Vous m'avez dit que…\" / \"You mentioned earlier that…\") "
        "then ask one open-ended question that probes a moment, a "
        "decision, or a friction relevant to their use_case.\n\n"
        f"Constraints:\n"
        f"- Write in {lang_label}.\n"
        "- 50-80 words. ONE question only — no multi-part.\n"
        "- Reference their world (transit / fintech / retail / etc.) "
        "  — NOT a generic 'tell me about your onboarding'.\n"
        "- Sound like a participant interviewer, not a chatbot.\n"
        "- Plain prose. No JSON, no preamble."
    )

    try:
        client = anthropic.Anthropic(
            api_key=settings.ANTHROPIC_API_KEY,
            timeout=httpx.Timeout(15.0),
        )
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=250,
            temperature=0.5,
            system=system,
            messages=[{"role": "user", "content": "Generate the question now."}],
        )
        text = (resp.content[0].text or "").strip()
        if not text:
            return None
        company.demo_opening_question_text = text
        company.demo_opening_question_at = datetime.utcnow()
        return text
    except Exception:  # noqa: BLE001 — silent fallback to static question
        logger.exception("Demo opening question Haiku call failed")
        return None
