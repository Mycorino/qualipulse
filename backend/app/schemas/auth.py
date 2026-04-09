from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


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

    model_config = {"from_attributes": True}


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    preferred_language: Optional[str] = None
