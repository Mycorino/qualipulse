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
    prompt = f"""A new user of a qualitative research platform wrote this about what they want to learn from their interviews:

"{goals_freeform.strip()}"

Classify this into 1-3 of the following buckets. Return ONLY a comma-separated list of bucket keys, nothing else. No preamble, no explanation, no markdown.

Available buckets:
{bucket_list}

Return format: "key1,key2" (1-3 keys, lowercase, comma-separated)"""

    try:
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=64,
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
