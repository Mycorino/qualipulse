"""Backfill business context from a manually-typed company name.

For freemail signups (gmail, etc.) we don't run the email-domain
prefetch — but the wizard does capture a typed company name. If
the name is a known company (Legalstart, RATP, BNP Paribas, …),
Haiku can produce a useful business summary + industry without any
web search.

Approach: ask Haiku directly. LLM recognition is excellent for
well-known companies; for obscure names it returns null cleanly.

Fire-and-forget — failure must never block the wizard.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from app.services._clients import get_anthropic_client

from app.config import settings
from app.models.company import Company
from app.services.website_intelligence import _PREDEFINED_INDUSTRIES

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5"


def _industry_list() -> str:
    return " | ".join(_PREDEFINED_INDUSTRIES)


def backfill_business_from_name(
    company: Company, *, force: bool = False
) -> bool:
    """Populate ``business_summary`` + ``industry`` for a company whose
    only known signal is the typed name. Returns True if anything was
    written. Caller commits the session.

    No-op when:
      - business_summary is already set (don't overwrite)
      - Anthropic API key is missing
      - the typed name is too short / blank
      - Haiku says it doesn't recognise the company

    Safe to call on any company; safe to retry."""
    if not force and (company.business_summary or "").strip():
        return False
    name = (company.name or "").strip()
    if len(name) < 2:
        return False
    if not settings.ANTHROPIC_API_KEY:
        return False

    lang = (company.preferred_language or "en").lower()
    lang_label = "French" if lang == "fr" else "English"

    system = (
        "You are helping a B2B SaaS onboard a researcher. They just "
        "typed their company's name. Decide whether you recognise the "
        "company well enough to write a factual, third-person summary "
        "and classify its industry. If you don't recognise the name "
        "(or are unsure), return null fields — do NOT invent a "
        "business.\n\n"
        f"WRITE THE SUMMARY IN {lang_label.upper()} ONLY.\n\n"
        "Output JSON with EXACTLY this shape:\n"
        '{"summary": "<2-3 sentence factual description: what the '
        'company sells, who their customers are. Plain prose, no '
        'marketing fluff, no emojis. NULL if you don\'t recognise '
        'this company.>",\n'
        f'"industry": "<one of: {_industry_list()}. NULL if unsure.>"}}\n\n'
        "Critical rules:\n"
        "- If the name is generic, ambiguous, a person's name, or you "
        "simply don't recognise it, return both fields as null. Better "
        "no data than confabulation.\n"
        "- Classify industry by the company's primary revenue "
        "activity, not by what tech they use.\n"
        "- Return ONLY the JSON object, no prose, no markdown fences."
    )

    user = f"Company name: {name}"

    try:
        client = get_anthropic_client(15.0)
        resp = client.messages.create(
            model=_MODEL,
            max_tokens=300,
            temperature=0.1,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()
        parsed = json.loads(raw)
        summary = parsed.get("summary")
        industry = parsed.get("industry")

        wrote = False
        if isinstance(summary, str) and summary.strip():
            company.business_summary = summary.strip()
            wrote = True
        if isinstance(industry, str) and industry.strip():
            # Only set industry if not already user-set.
            if not (company.industry or "").strip():
                company.industry = industry.strip()
                wrote = True
        return wrote
    except Exception:  # noqa: BLE001 — silent fallback
        logger.exception("Company-name backfill via Haiku failed")
        return False
