"""Canonical plan catalogue for the credits-based billing system.

Two families:

1. **Legacy plans** (``legacy_starter`` / ``legacy_team`` / ``legacy_lab``) —
   preserve the old tier-based behaviour for existing accounts. They have
   ``is_legacy=True``, ``credit_period='legacy_none'`` and
   ``included_credits=None``. Quota decisions for these plans defer to
   ``feature_gates.require_participant_limit`` (existing logic).

2. **New plans** (``trial`` / ``exploration`` / ``team`` / ``agency`` /
   ``enterprise``) — credits-based. ``BillingService.can_start_interview``
   checks the per-period credit balance. ``team`` here is the new €299/mo
   plan, NOT the legacy €99/mo tier (that one is ``legacy_team``).

Edit this file when adding a plan, then run::

    python -m app.scripts.seed_plans

(or just restart the API — ``main.py`` calls ``ensure_plans_seeded`` on
startup so the table is always in sync with this catalogue.)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanSpec:
    id: str
    public_name: str
    description: str
    is_public: bool = True
    is_legacy: bool = False
    is_custom: bool = False
    monthly_price_cents: int | None = None
    annual_price_cents: int | None = None
    currency: str = "EUR"
    included_credits: int | None = None
    credit_period: str = "monthly"
    max_editors: int | None = None
    max_viewers: int | None = None
    max_active_projects: int | None = None
    overage_price_cents: int | None = None
    overage_enabled_default: bool = False
    sort_order: int = 0
    entitlements: dict[str, Any] = field(default_factory=dict)


# ── Legacy plans (preserve current tier-based behaviour) ──────────────────────
# These mirror the existing ``feature_gates.TIER_LIMITS`` 1:1 so existing
# accounts see no functional change. ``is_legacy=True`` flips quota checks
# back to ``require_participant_limit`` instead of credit-based.

LEGACY_STARTER = PlanSpec(
    id="legacy_starter",
    public_name="Starter (legacy)",
    description="Legacy 49€ Starter plan. Existing customers stay here until they upgrade.",
    is_public=False,
    is_legacy=True,
    monthly_price_cents=4900,
    credit_period="legacy_none",
    max_editors=1,
    max_active_projects=1,
    sort_order=10,
    entitlements={
        "csv_export": False,
        "ai_analysis": True,
        "custom_branding": False,
        "team_workspace": False,
        "max_participants_per_project": 10,
        "max_questions_per_guide": 10,
        "max_links_per_project": 2,
        "legacy_tier": "starter",
    },
)

LEGACY_TEAM = PlanSpec(
    id="legacy_team",
    public_name="Team (legacy)",
    description="Legacy 99€ Team plan. Existing customers stay here until they upgrade.",
    is_public=False,
    is_legacy=True,
    monthly_price_cents=9900,
    credit_period="legacy_none",
    max_editors=3,
    max_active_projects=5,
    sort_order=11,
    entitlements={
        "csv_export": True,
        "ai_analysis": True,
        "custom_branding": False,
        "team_workspace": True,
        "max_participants_per_project": 50,
        "max_questions_per_guide": 15,
        "max_links_per_project": 3,
        "legacy_tier": "team",
    },
)

LEGACY_LAB = PlanSpec(
    id="legacy_lab",
    public_name="Lab (legacy)",
    description="Legacy 199€ Lab plan. Existing customers stay here until they upgrade.",
    is_public=False,
    is_legacy=True,
    monthly_price_cents=19900,
    credit_period="legacy_none",
    max_editors=10,
    max_active_projects=None,
    sort_order=12,
    entitlements={
        "csv_export": True,
        "ai_analysis": True,
        "custom_branding": True,
        "team_workspace": True,
        "max_participants_per_project": 500,
        "max_questions_per_guide": 30,
        "max_links_per_project": 10,
        "legacy_tier": "lab",
    },
)

# ── New plans (credits-based) ─────────────────────────────────────────────────

TRIAL = PlanSpec(
    id="trial",
    public_name="Trial",
    description="14-day trial with 10 included credits. No credit card required.",
    is_public=False,  # not on the pricing page; assigned automatically on signup
    monthly_price_cents=0,
    included_credits=10,
    credit_period="trial_total",
    max_editors=1,
    max_viewers=0,
    max_active_projects=1,
    sort_order=0,
    entitlements={
        "csv_export": False,
        "pdf_export": True,
        "public_report_share": False,
        "custom_branding": False,
        "team_workspace": False,
        "client_workspaces": False,
        "sso": False,
        "api_access": False,
        "ai_analysis": True,
    },
)

EXPLORATION = PlanSpec(
    id="exploration",
    public_name="Exploration",
    description="For solo researchers running a few studies a month.",
    monthly_price_cents=8900,
    annual_price_cents=89000,
    included_credits=25,
    credit_period="monthly",
    max_editors=1,
    max_viewers=3,
    max_active_projects=3,
    overage_price_cents=700,  # €7/credit
    overage_enabled_default=False,
    sort_order=1,
    entitlements={
        "csv_export": True,
        "pdf_export": True,
        "public_report_share": True,
        "custom_branding": False,
        "team_workspace": False,
        "client_workspaces": False,
        "sso": False,
        "api_access": False,
        "ai_analysis": True,
    },
)

TEAM = PlanSpec(
    id="team",
    public_name="Team",
    description="For research teams running studies in parallel.",
    monthly_price_cents=29900,
    annual_price_cents=299000,
    included_credits=100,
    credit_period="monthly",
    max_editors=3,
    max_viewers=None,
    max_active_projects=20,
    overage_price_cents=600,  # €6/credit
    overage_enabled_default=False,
    sort_order=2,
    entitlements={
        "csv_export": True,
        "pdf_export": True,
        "public_report_share": True,
        "custom_branding": False,
        "team_workspace": True,
        "client_workspaces": False,
        "sso": False,
        "api_access": False,
        "ai_analysis": True,
        # V2 rollover knobs (read by the rollover service, not enforced in V1).
        "credit_rollover_days": 30,
        "credit_rollover_cap_ratio": 0.25,
    },
)

AGENCY = PlanSpec(
    id="agency",
    public_name="Agency",
    description="For agencies running research for multiple clients.",
    monthly_price_cents=79900,
    annual_price_cents=799000,
    included_credits=300,
    credit_period="monthly",
    max_editors=8,
    max_viewers=None,
    max_active_projects=None,
    overage_price_cents=500,  # €5/credit
    overage_enabled_default=False,
    sort_order=3,
    entitlements={
        "csv_export": True,
        "pdf_export": True,
        "public_report_share": True,
        "custom_branding": True,
        "team_workspace": True,
        "client_workspaces": True,
        "sso": False,
        "api_access": True,
        "ai_analysis": True,
        "credit_rollover_days": 90,
        "credit_rollover_cap_ratio": 0.40,
    },
)

ENTERPRISE = PlanSpec(
    id="enterprise",
    public_name="Enterprise",
    description="Custom annual contract. Talk to us.",
    is_public=True,
    is_custom=True,
    credit_period="custom",
    max_editors=None,
    max_viewers=None,
    max_active_projects=None,
    overage_enabled_default=True,
    sort_order=4,
    entitlements={
        "csv_export": True,
        "pdf_export": True,
        "public_report_share": True,
        "custom_branding": True,
        "team_workspace": True,
        "client_workspaces": True,
        "sso": True,
        "api_access": True,
        "ai_analysis": True,
        "audit_logs": True,
        "dpa": True,
        "retention_policy": True,
    },
)

ALL_PLANS: tuple[PlanSpec, ...] = (
    LEGACY_STARTER,
    LEGACY_TEAM,
    LEGACY_LAB,
    TRIAL,
    EXPLORATION,
    TEAM,
    AGENCY,
    ENTERPRISE,
)

# Mapping from existing ``Company.subscription_tier`` values to the legacy
# plan rows we'll backfill them onto. Older aliases ('free' / 'solo' / 'pro')
# collapse to their canonical equivalents.
LEGACY_TIER_TO_PLAN_ID: dict[str, str] = {
    "free": "legacy_starter",
    "starter": "legacy_starter",
    "solo": "legacy_starter",
    "team": "legacy_team",
    "lab": "legacy_lab",
    "pro": "legacy_lab",
    "enterprise": "enterprise",
}
