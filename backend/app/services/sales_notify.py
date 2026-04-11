"""Sales pipeline notifications.

Fire-and-forget Slack messages that go out when high-signal events happen
(new signup completes onboarding, a user hits their trial limit, etc.) so the
founding team can reach out while the account is still warm.

All functions swallow exceptions — a broken webhook must never block a user.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import settings
from app.services.slack import _post

if TYPE_CHECKING:
    from app.models.company import Company

logger = logging.getLogger("auto_interview.sales_notify")


# Weights for a rough lead score — bigger number = warmer lead.
# Tuned to bias toward B2B SaaS mid-market PMs with buyer authority, which
# is our current ICP.
_COMPANY_SIZE_SCORE = {
    "Just me": 1,
    "2–10": 3,
    "2-10": 3,
    "11–50": 5,
    "11-50": 5,
    "51–200": 7,
    "51-200": 7,
    "201–1000": 6,
    "201-1000": 6,
    "1000+": 4,  # harder to close, long cycles
}

_ROLE_SCORE = {
    "Product Manager": 6,
    "Researcher": 5,
    "Designer": 3,
    "Founder": 4,
    "Marketer": 3,
    "Consultant": 2,
    "Academic": 1,
    "Other": 1,
}

_INDUSTRY_SCORE = {
    "SaaS / Tech": 5,
    "Consumer Brands": 4,
    "Agency": 3,
    "Healthcare": 3,
    "Government": 2,
    "Academia": 1,
    "Other": 1,
}

_INTERVIEWS_TARGET_SCORE = {
    "0-5": 1,
    "5-20": 4,
    "20-50": 7,
    "50+": 10,
}

_DECISION_ROLE_SCORE = {
    "buyer": 8,
    "influencer": 4,
    "user": 2,
    "evaluator": 3,
}

_FREE_EMAIL_DOMAINS = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "icloud.com", "proton.me", "protonmail.com", "aol.com",
    "mail.com", "gmx.com", "yandex.com",
}


def _score_lead(company: "Company") -> tuple[int, str]:
    """Compute a 0-100ish lead score + a qualitative label.

    The score is deliberately coarse — its job is to help the sales human
    decide which new signups to reach out to first, not to make an automated
    decision.
    """
    score = 0
    score += _COMPANY_SIZE_SCORE.get(company.company_size or "", 0)
    score += _ROLE_SCORE.get(company.role or "", 0)
    score += _INDUSTRY_SCORE.get(company.industry or "", 0)
    score += _INTERVIEWS_TARGET_SCORE.get(company.interviews_per_month_target or "", 0)
    score += _DECISION_ROLE_SCORE.get(company.decision_role or "", 0)

    # Work-email bonus — free-email signups are usually hobbyists.
    email = (company.email or "").lower()
    domain = email.split("@")[-1] if "@" in email else ""
    if domain and domain not in _FREE_EMAIL_DOMAINS:
        score += 5

    # Current-tool signal — if they're already paying for Dovetail/UserTesting
    # they've proven budget exists.
    tool = (company.current_tool or "").lower()
    if any(k in tool for k in ("dovetail", "usertesting", "userinterviews", "respondent")):
        score += 5

    if score >= 25:
        label = "🔥 HOT"
    elif score >= 15:
        label = "🌡️ WARM"
    elif score >= 7:
        label = "❄️ COOL"
    else:
        label = "🧊 COLD"

    return score, label


def _build_payload(company: "Company") -> dict:
    score, label = _score_lead(company)

    fields: list[dict] = []

    def _add(title: str, value: str | None):
        if value:
            fields.append({"type": "mrkdwn", "text": f"*{title}*\n{value}"})

    _add("Company", company.name)
    _add("Email", company.email)
    _add("Size", company.company_size)
    _add("Role", company.role)
    _add("Industry", company.industry)
    _add("Region", company.primary_region)
    _add("Website", company.website_url)
    _add("Interviews/mo target", company.interviews_per_month_target)
    _add("Current tool", company.current_tool)
    _add("Decision role", company.decision_role)
    _add("Goal buckets", company.goals_classification)

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{label} New signup ({score} pts): {company.name}",
            },
        },
    ]

    if company.business_summary:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Business:* {company.business_summary[:600]}",
                },
            }
        )

    if company.goals_freeform:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*What they want to learn:*\n> {company.goals_freeform[:600]}",
                },
            }
        )

    # Slack section blocks cap at 10 fields. We only collect ~11 so slice to be safe.
    if fields:
        blocks.append({"type": "section", "fields": fields[:10]})

    return {
        "text": f"{label} New signup: {company.name} ({score} pts)",
        "blocks": blocks,
    }


def notify_new_signup(company: "Company") -> None:
    """Post a new-signup notification to the sales Slack channel.

    Noop when ``SALES_SLACK_WEBHOOK_URL`` is not configured.
    """
    webhook = settings.SALES_SLACK_WEBHOOK_URL
    if not webhook:
        return
    try:
        payload = _build_payload(company)
        _post(webhook, payload)
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to build sales signup notification for %s", company.email)
