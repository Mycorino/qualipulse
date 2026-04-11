from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    # Plan selected on the landing page (free/starter/team/lab). Optional —
    # defaults to "starter" with 14-day Team-level trial if omitted.
    plan: Optional[str] = None
    # Affiliate referral code, if present
    ref_code: Optional[str] = None
    # UI locale at signup time — used to pick the language of the welcome
    # and verification emails. Stored on the company record.
    preferred_language: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str


class OnboardingProfileRequest(BaseModel):
    """Company details collected during onboarding."""
    name: Optional[str] = None
    company_size: Optional[str] = None
    role: Optional[str] = None
    industry: Optional[str] = None
    use_case: Optional[str] = None
    website_url: Optional[str] = None
    business_summary: Optional[str] = None
    research_experience: Optional[str] = None
    primary_region: Optional[str] = None
    goals_freeform: Optional[str] = None
    # Account language — drives email locale, AI generation language
    # (research wizard suggestions, interview guide drafting), and the
    # default project language. Set at signup from i18n.language and
    # confirmable in onboarding step 2.
    preferred_language: Optional[str] = None

    # Business context (grounds AI analysis + research suggestions)
    value_proposition: Optional[str] = None
    primary_competitors: Optional[str] = None
    product_stage: Optional[str] = None
    customer_type: Optional[str] = None

    # Qualification signals (routes leads for sales)
    interviews_per_month_target: Optional[str] = None
    current_tool: Optional[str] = None
    decision_role: Optional[str] = None


class CompanyResponse(BaseModel):
    id: str
    name: str
    email: str
    email_verified: bool = False
    company_size: Optional[str] = None
    role: Optional[str] = None
    industry: Optional[str] = None
    use_case: Optional[str] = None
    onboarding_completed: bool = False
    subscription_tier: str = "starter"
    trial_ends_at: Optional[datetime] = None
    created_at: datetime
    website_url: Optional[str] = None
    business_summary: Optional[str] = None
    research_experience: Optional[str] = None
    primary_region: Optional[str] = None
    goals_freeform: Optional[str] = None
    preferred_language: str = "fr"
    slack_webhook_url: Optional[str] = None
    value_proposition: Optional[str] = None
    primary_competitors: Optional[str] = None
    product_stage: Optional[str] = None
    customer_type: Optional[str] = None
    interviews_per_month_target: Optional[str] = None
    current_tool: Optional[str] = None
    decision_role: Optional[str] = None
    goals_classification: Optional[str] = None

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    preferred_language: Optional[str] = None


class SlackWebhookUpdate(BaseModel):
    slack_webhook_url: Optional[str] = None
