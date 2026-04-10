import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.limiter import limiter
from app.models.company import Company, EmailVerificationToken, PasswordResetToken
from app.models.affiliate import Affiliate, AffiliateReferral
from app.schemas.auth import (
    CompanyResponse,
    LoginRequest,
    OnboardingProfileRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    SignupRequest,
    SlackWebhookUpdate,
    TokenResponse,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.services.email import (
    send_newsletter_welcome,
    send_password_reset,
    send_verification_email,
    send_welcome,
)
from app.services.website_intelligence import (
    WebsiteIntelligenceError,
    fetch_website_summary,
)

logger = logging.getLogger("auto_interview.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def signup(request: Request, body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.query(Company).filter(Company.email == body.email.lower().strip()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Try signing in instead.",
        )

    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )

    # Resolve plan selection from the landing page.
    # Free tier → no trial (they get the free tier limits permanently).
    # Paid tiers → default starter + 14-day team-level trial.
    requested_plan = (body.plan or "").strip().lower()
    if requested_plan == "free":
        tier = "free"
        trial_ends = None
    else:
        tier = "starter"
        trial_ends = datetime.utcnow() + timedelta(days=14)

    company = Company(
        name=body.name.strip(),
        email=body.email.lower().strip(),
        password_hash=hash_password(body.password),
        subscription_tier=tier,
        trial_ends_at=trial_ends,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    logger.info("New company signup: %s", company.email)

    # Check for affiliate referral code (from query params or body)
    ref_code = None
    if hasattr(body, "ref_code") and body.ref_code:
        ref_code = body.ref_code
    else:
        # Try to get from query params
        ref_code = request.query_params.get("ref") if hasattr(request, "query_params") else None

    if ref_code:
        affiliate = db.query(Affiliate).filter(Affiliate.code == ref_code.lower()).first()
        if affiliate and affiliate.status == "active":
            # Create affiliate referral
            referral = AffiliateReferral(
                affiliate_id=affiliate.id,
                referred_company_id=company.id,
            )
            db.add(referral)
            db.commit()
            logger.info("Affiliate referral tracked: %s -> %s", affiliate.code, company.email)

    # Create email verification token
    verification_token = EmailVerificationToken(
        company_id=company.id,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(verification_token)
    db.commit()

    # Send verification email
    verify_url = f"{settings.APP_BASE_URL}/verify-email?token={verification_token.token}"
    send_verification_email(company.email, company.name, verify_url)

    # Also send welcome
    send_welcome(company.email, company.name)

    return TokenResponse(
        access_token=create_access_token({"sub": company.id}),
        refresh_token=create_refresh_token({"sub": company.id}),
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    company = db.query(Company).filter(Company.email == body.email.lower().strip()).first()
    if not company or not verify_password(body.password, company.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    logger.info("Login: %s", company.email)
    return TokenResponse(
        access_token=create_access_token({"sub": company.id}),
        refresh_token=create_refresh_token({"sub": company.id}),
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    payload = decode_refresh_token(body.refresh_token)
    company_id: str | None = payload.get("sub")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    return TokenResponse(
        access_token=create_access_token({"sub": company.id}),
        refresh_token=create_refresh_token({"sub": company.id}),
    )


# ââ Email Verification ââââââââââââââââââââââââââââââââââââââââââââââââ

@router.post("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):
    """Verify email address using the token from the verification email."""
    token_row = db.query(EmailVerificationToken).filter(
        EmailVerificationToken.token == token,
        EmailVerificationToken.used.is_(False),
    ).first()

    if not token_row or token_row.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired.",
        )

    company = db.query(Company).filter(Company.id == token_row.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")

    company.email_verified = True
    token_row.used = True
    db.commit()

    logger.info("Email verified for %s", company.email)
    return {"message": "Email verified successfully"}


@router.post("/resend-verification")
@limiter.limit("3/minute")
def resend_verification(
    request: Request,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Resend the verification email. Requires authentication."""
    if company.email_verified:
        return {"message": "Email is already verified"}

    # Expire existing tokens
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.company_id == company.id,
        EmailVerificationToken.used.is_(False),
    ).delete()

    # Create new token
    verification_token = EmailVerificationToken(
        company_id=company.id,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    db.add(verification_token)
    db.commit()

    verify_url = f"{settings.APP_BASE_URL}/verify-email?token={verification_token.token}"
    send_verification_email(company.email, company.name, verify_url)

    logger.info("Verification email resent to %s", company.email)
    return {"message": "Verification email sent"}


# ââ Password Reset ââââââââââââââââââââââââââââââââââââââââââââââââââââ

@router.post("/password-reset/request")
@limiter.limit("5/minute")
def request_password_reset(request: Request, body: PasswordResetRequest, db: Session = Depends(get_db)):
    """Always returns 200 to prevent email enumeration."""
    company = db.query(Company).filter(Company.email == body.email.lower().strip()).first()
    if company:
        # Expire any existing tokens
        db.query(PasswordResetToken).filter(
            PasswordResetToken.company_id == company.id,
            PasswordResetToken.used.is_(False),
        ).delete()
        token = PasswordResetToken(
            company_id=company.id,
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        db.add(token)
        db.commit()
        reset_url = f"{settings.APP_BASE_URL}/reset-password?token={token.token}"
        send_password_reset(company.email, reset_url)
        logger.info("Password reset requested for %s", company.email)
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    if len(body.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )
    token_row = db.query(PasswordResetToken).filter(
        PasswordResetToken.token == body.token,
        PasswordResetToken.used.is_(False),
    ).first()
    if not token_row or token_row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
    company = db.query(Company).filter(Company.id == token_row.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    company.password_hash = hash_password(body.new_password)
    token_row.used = True
    db.commit()
    logger.info("Password reset completed for %s", company.email)
    return {"message": "Password updated successfully"}


# ââ Profile & Onboarding ââââââââââââââââââââââââââââââââââââââââââââââââ

@router.get("/me", response_model=CompanyResponse)
def get_me(company: Company = Depends(get_current_company)) -> CompanyResponse:
    return CompanyResponse.model_validate(company)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.patch("/me", response_model=CompanyResponse)
def update_profile(
    body: dict,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Update the authenticated company's profile (name, preferred_language)."""
    if "name" in body and body["name"]:
        company.name = str(body["name"]).strip()
    if "preferred_language" in body and body["preferred_language"] in ("en", "fr"):
        company.preferred_language = body["preferred_language"]
    db.commit()
    db.refresh(company)
    return CompanyResponse.model_validate(company)


@router.post("/website-intel")
@limiter.limit("5/minute")
async def website_intel(
    request: Request,
    body: dict,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Fetch a website and generate a business summary + industry using Claude.

    Uses the company's ``preferred_language`` so the prose matches the UI
    locale the user is currently filling the onboarding form in. Persists
    the URL, summary, and detected industry to the company record.
    """
    url = (body.get("website_url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="website_url is required")

    language = company.preferred_language or "en"

    try:
        result = await fetch_website_summary(
            url,
            language=language,
            db=db,
            company_id=company.id,
        )
    except WebsiteIntelligenceError as exc:
        # Still persist the URL so we don't ask for it again; just skip the summary.
        company.website_url = url
        db.commit()
        logger.info(
            "Website intel failed for %s (%s): %s", company.email, exc.code, url
        )
        raise HTTPException(
            status_code=422,
            detail={"code": exc.code, "message": exc.message},
        )

    summary = result.get("summary", "")
    industry = result.get("industry")

    company.website_url = url
    company.business_summary = summary
    if industry:
        company.industry = industry
    db.commit()

    logger.info(
        "Website intel generated for %s: %s (industry=%s)",
        company.email,
        url,
        industry,
    )
    return {"business_summary": summary, "industry": industry}


@router.patch("/onboarding")
def save_onboarding_profile(
    body: OnboardingProfileRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Save company profile details during onboarding (intermediate save, doesn't mark complete)."""
    if body.name:
        company.name = body.name.strip()
    if body.company_size:
        company.company_size = body.company_size
    if body.role:
        company.role = body.role
    if body.industry:
        company.industry = body.industry
    if body.use_case:
        company.use_case = body.use_case
    if body.website_url is not None:
        company.website_url = body.website_url
    if body.business_summary is not None:
        company.business_summary = body.business_summary
    if body.research_experience is not None:
        company.research_experience = body.research_experience
    if body.primary_region is not None:
        company.primary_region = body.primary_region
    db.commit()
    logger.info("Onboarding profile saved for %s", company.email)
    return CompanyResponse.model_validate(company)


@router.post("/onboarding")
def complete_onboarding(
    body: OnboardingProfileRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Save company profile details and mark onboarding as complete."""
    if body.name:
        company.name = body.name.strip()
    if body.company_size:
        company.company_size = body.company_size
    if body.role:
        company.role = body.role
    if body.industry:
        company.industry = body.industry
    if body.use_case:
        company.use_case = body.use_case
    if body.website_url is not None:
        company.website_url = body.website_url
    if body.business_summary is not None:
        company.business_summary = body.business_summary
    if body.research_experience is not None:
        company.research_experience = body.research_experience
    if body.primary_region is not None:
        company.primary_region = body.primary_region
    if body.goals_freeform is not None:
        company.goals_freeform = body.goals_freeform
    company.onboarding_completed = True
    db.commit()
    logger.info("Onboarding completed for %s", company.email)
    return CompanyResponse.model_validate(company)


@router.post("/change-password")
def change_password(
    body: ChangePasswordRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Change password â requires current password verification."""
    if not verify_password(body.current_password, company.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    company.password_hash = hash_password(body.new_password)
    db.commit()
    logger.info("Password changed for %s", company.email)
    return {"message": "Password updated successfully"}


# ── Integrations: Slack ───────────────────────────────────────────────


def _validate_slack_url(url: str | None) -> str | None:
    """Normalize + validate a Slack webhook URL. Returns cleaned URL or raises."""
    if url is None:
        return None
    cleaned = url.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("https://hooks.slack.com/services/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack webhook URL must start with https://hooks.slack.com/services/",
        )
    if len(cleaned) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slack webhook URL is too long.",
        )
    return cleaned


@router.put("/me/slack")
def update_slack_webhook(
    body: SlackWebhookUpdate,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Save (or clear) the company's Slack webhook URL."""
    cleaned = _validate_slack_url(body.slack_webhook_url)
    company.slack_webhook_url = cleaned
    db.commit()
    logger.info("Slack webhook %s for %s", "set" if cleaned else "cleared", company.email)
    return {"slack_webhook_url": cleaned}


@router.post("/me/slack/test")
def test_slack_webhook(
    body: SlackWebhookUpdate,
    company: Company = Depends(get_current_company),
):
    """Send a test message to the provided (or saved) Slack webhook URL."""
    from app.services.slack import send_test_message

    url = _validate_slack_url(body.slack_webhook_url) or company.slack_webhook_url
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Slack webhook URL configured.",
        )
    ok = send_test_message(url)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Slack webhook call failed. Double-check the URL and try again.",
        )
    return {"message": "Test message sent"}


class NewsletterSubscribe(BaseModel):
    email: str


@router.post("/newsletter")
@limiter.limit("5/minute")
def subscribe_newsletter(request: Request, body: NewsletterSubscribe):
    """Subscribe to newsletter â just sends a welcome email for now."""
    send_newsletter_welcome(body.email.lower().strip())
    logger.info("Newsletter subscription: %s", body.email)
    return {"message": "Subscribed successfully"}
