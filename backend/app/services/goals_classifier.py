"""Classify the free-form `goals_freeform` onboarding answer into stable buckets.

Free-form goals are rich qualitative data but useless for analytics and sales
routing unless they're normalised. This service asks Claude to map whatever the
user typed into one or more of a stable taxonomy.

Output is a comma-separated list of bucket keys so we can store it in a single
short ``String(200)`` column without a separate table. Callers catch all
exceptions and fall back to ``None`` so a classifier outage never blocks
onboarding completion.
"""

from __future__ import annotations

import logging

import anthropic

from app.config import settings

logger = logging.getLogger("auto_interview.goals_classifier")


GOAL_BUCKETS = {
    "product_discovery": "Explore new product ideas or unmet needs",
    "feature_validation": "Validate a specific feature or concept before building",
    "customer_retention": "Understand churn, satisfaction, or loyalty drivers",
    "pricing_research": "Test pricing, willingness to pay, or packaging",
    "positioning": "Refine messaging, brand, or market positioning",
    "competitor_research": "Understand how users see competitors or alternatives",
    "usability_testing": "Watch users try something and find friction",
    "market_sizing": "Understand a segment or TAM qualitatively",
    "onboarding_optimization": "Improve activation, first-run, or getting-started flow",
    "other": "Something else that doesn't fit the above",
}


def classify_goals(goals_freeform: str, timeout: float = 10.0) -> str | None:
    """Map a free-form goals string to a comma-separated list of bucket keys.

    Returns ``None`` if the API key is missing, the call fails, or the model
    returns nothing usable. Callers should treat ``None`` as "classification
    unknown" and continue, not as an error.
    """
    if not goals_freeform or not goals_freeform.strip():
        return None
    if not settings.ANTHROPIC_API_KEY:
        return None

    bucket_list = "\n".join(f"- {key}: {desc}" for key, desc in GOAL_BUCKETS.items())

    system_msg = (
        "You are a strict multi-label classifier. You map free-form research goals to a "
        "fixed taxonomy. Output is consumed by code — any prose, markdown, or extra "
        "tokens will break it. Output ONLY a comma-separated list of bucket keys."
    )

    prompt = f"""<input>
{goals_freeform.strip()}
</input>

<taxonomy>
{bucket_list}
</taxonomy>

<rules>
- Pick 1-3 buckets that BEST fit the input. Prefer fewer over more — only add a second/third \
bucket if the input clearly spans multiple distinct goals.
- Use "other" ONLY when no specific bucket reasonably applies. Never combine "other" with \
another key — if a specific bucket fits, use that instead.
- Lowercase keys, comma-separated, no spaces, no quotes, no trailing punctuation.
- Bad: `pricing_research, positioning` (space). Good: `pricing_research,positioning`.
</rules>

Output the keys now."""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=64,
            temperature=0.3,
            system=system_msg,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        # Defensive: strip anything that isn't a known bucket key
        keys = [k.strip().lower() for k in raw.split(",") if k.strip()]
        valid = [k for k in keys if k in GOAL_BUCKETS]
        if not valid:
            return None
        return ",".join(valid[:3])
    except Exception:
        logger.exception("Goals classification failed")
        return None
