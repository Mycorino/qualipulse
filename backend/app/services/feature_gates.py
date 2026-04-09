"""
Feature gating based on subscription tier.
Centralises all tier limit checks.

Canonical tiers: starter (€49) | team (€99) | lab (€199) | enterprise (custom)
Legacy DB aliases: free → starter, solo → starter, pro → lab
"""
from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status


@dataclass
class TierLimits:
    name: str
    max_projects: int                  # -1 = unlimited
    max_participants_per_project: int
    max_questions_per_guide: int
    ai_analysis: bool
    export_csv: bool
    custom_branding: bool
    team_members: int                  # max collaborators including owner
    interview_links_per_project: int
    price_monthly_usd: int             # stored in EUR; field name kept for compat


TIER_LIMITS: dict[str, TierLimits] = {
    "starter": TierLimits(
        name="Starter",
        max_projects=1,
        max_participants_per_project=10,
        max_questions_per_guide=10,
        ai_analysis=True,
        export_csv=False,
        custom_branding=False,
        team_members=1,
        interview_links_per_project=2,
        price_monthly_usd=49,
    ),
    "team": TierLimits(
        name="Team",
        max_projects=5,
        max_participants_per_project=50,
        max_questions_per_guide=15,
        ai_analysis=True,
        export_csv=True,
        custom_branding=False,
        team_members=3,
        interview_links_per_project=3,
        price_monthly_usd=99,
    ),
    "lab": TierLimits(
        name="Lab",
        max_projects=-1,
        max_participants_per_project=500,
        max_questions_per_guide=30,
        ai_analysis=True,
        export_csv=True,
        custom_branding=True,
        team_members=10,
        interview_links_per_project=10,
        price_monthly_usd=199,
    ),
    "enterprise": TierLimits(
        name="Enterprise",
        max_projects=-1,
        max_participants_per_project=-1,
        max_questions_per_guide=-1,
        ai_analysis=True,
        export_csv=True,
        custom_branding=True,
        team_members=-1,
        interview_links_per_project=-1,
        price_monthly_usd=0,  # custom pricing
    ),
}

# Legacy aliases — keep existing DB rows working after rename
TIER_LIMITS["free"] = TIER_LIMITS["starter"]    # old free tier → starter
TIER_LIMITS["solo"] = TIER_LIMITS["starter"]    # old solo tier → starter
TIER_LIMITS["pro"] = TIER_LIMITS["lab"]         # old pro tier → lab

DEFAULT_TIER = "starter"

# Canonical tier IDs (no legacy aliases)
CANONICAL_TIERS = ("starter", "team", "lab", "enterprise")


def get_limits(tier: str) -> TierLimits:
    """Get limits for a raw tier string (no trial logic)."""
    return TIER_LIMITS.get(tier, TIER_LIMITS[DEFAULT_TIER])


def get_effective_limits(company) -> TierLimits:
    """Get limits for a company, accounting for active trial.

    If the company is on the starter tier but has an active trial
    (trial_ends_at is in the future), return team-level limits.
    """
    tier = company.subscription_tier or DEFAULT_TIER
    limits = TIER_LIMITS.get(tier, TIER_LIMITS[DEFAULT_TIER])

    # Starter/legacy-free/solo users with active trial get team-level limits
    if tier in ("starter", "free", "solo") and getattr(company, "trial_ends_at", None):
        if company.trial_ends_at > datetime.utcnow():
            limits = TIER_LIMITS["team"]

    return limits


def require_feature(company, feature: str) -> None:
    """Raise 403 if company's tier doesn't have the feature."""
    limits = get_effective_limits(company)
    if not getattr(limits, feature, False):
        tier_name = limits.name
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This feature requires a higher plan. You are on the {tier_name} plan.",
        )


def require_project_limit(company, current_project_count: int) -> None:
    limits = get_effective_limits(company)
    if limits.max_projects != -1 and current_project_count >= limits.max_projects:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project limit reached ({limits.max_projects} projects on {limits.name} plan). Upgrade to create more.",
        )


def require_participant_limit(company, project, current_count: int) -> None:
    limits = get_effective_limits(company)
    if limits.max_participants_per_project != -1 and current_count >= limits.max_participants_per_project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Participant limit reached for this project ({limits.max_participants_per_project} on {limits.name} plan).",
        )


def require_question_limit(company, question_count: int) -> None:
    """Raise 403 if question_count exceeds the tier's max_questions_per_guide."""
    limits = get_effective_limits(company)
    if limits.max_questions_per_guide != -1 and question_count > limits.max_questions_per_guide:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Question limit exceeded ({limits.max_questions_per_guide} questions on {limits.name} plan). Upgrade to add more.",
        )


def require_link_limit(company, current_link_count: int) -> None:
    """Raise 403 if current_link_count has reached the tier's interview_links_per_project."""
    limits = get_effective_limits(company)
    if limits.interview_links_per_project != -1 and current_link_count >= limits.interview_links_per_project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Link limit reached ({limits.interview_links_per_project} links on {limits.name} plan). Upgrade to create more.",
        )
