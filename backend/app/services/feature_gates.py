"""
Feature gating based on subscription tier.
Centralises all tier limit checks.
"""
from dataclasses import dataclass
from fastapi import HTTPException, status


@dataclass
class TierLimits:
    name: str
    max_projects: int          # -1 = unlimited
    max_participants_per_project: int
    max_questions_per_guide: int
    ai_analysis: bool
    export_csv: bool
    custom_branding: bool
    team_members: int          # max collaborators including owner
    interview_links_per_project: int
    price_monthly_usd: int


TIER_LIMITS: dict[str, TierLimits] = {
    "free": TierLimits(
        name="Free",
        max_projects=1,
        max_participants_per_project=10,
        max_questions_per_guide=5,
        ai_analysis=False,
        export_csv=False,
        custom_branding=False,
        team_members=1,
        interview_links_per_project=1,
        price_monthly_usd=0,
    ),
    "starter": TierLimits(
        name="Starter",
        max_projects=5,
        max_participants_per_project=50,
        max_questions_per_guide=15,
        ai_analysis=True,
        export_csv=True,
        custom_branding=False,
        team_members=3,
        interview_links_per_project=3,
        price_monthly_usd=49,
    ),
    "pro": TierLimits(
        name="Pro",
        max_projects=-1,
        max_participants_per_project=500,
        max_questions_per_guide=30,
        ai_analysis=True,
        export_csv=True,
        custom_branding=True,
        team_members=10,
        interview_links_per_project=10,
        price_monthly_usd=149,
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


def get_limits(tier: str) -> TierLimits:
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])


def require_feature(company, feature: str) -> None:
    """Raise 403 if company's tier doesn't have the feature."""
    limits = get_limits(company.subscription_tier)
    if not getattr(limits, feature, False):
        tier_name = limits.name
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This feature requires a higher plan. You are on the {tier_name} plan.",
        )


def require_project_limit(company, current_project_count: int) -> None:
    limits = get_limits(company.subscription_tier)
    if limits.max_projects != -1 and current_project_count >= limits.max_projects:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Project limit reached ({limits.max_projects} projects on {limits.name} plan). Upgrade to create more.",
        )


def require_participant_limit(company, project, current_count: int) -> None:
    limits = get_limits(company.subscription_tier)
    if limits.max_participants_per_project != -1 and current_count >= limits.max_participants_per_project:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Participant limit reached for this project ({limits.max_participants_per_project} on {limits.name} plan).",
        )
