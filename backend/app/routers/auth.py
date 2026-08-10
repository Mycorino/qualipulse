import json
import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.limiter import limiter
from app.models.company import Company, EmailVerificationToken, PasswordResetToken
from app.models.affiliate import Affiliate, AffiliateReferral
from app.schemas.project import BrandingDefaultsPayload
from app.schemas.auth import (
    CompanyResponse,
    LoginRequest,
    OnboardingProfileRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PriorityUpdate,
    RefreshRequest,
    SignupRequest,
    SlackWebhookUpdate,
    TokenResponse,
)
from app.services.auth import (
    check_token_version,
    company_token_claims,
    consume_backup_code,
    create_2fa_pending_token,
    create_access_token,
    create_refresh_token,
    decode_2fa_pending_token,
    decode_refresh_token,
    generate_backup_codes,
    generate_totp_secret,
    hash_password,
    require_acceptable_password,
    totp_provisioning_uri,
    verify_password,
    verify_totp_code,
)
from app.services.analytics import emit_event
from app.services.demo_seeder import seed_demo_project
from app.services.email import (
    send_newsletter_welcome,
    send_password_reset,
    send_personalized_welcome,
    send_verification_email,
)
from app.services.website_intelligence import (
    WebsiteIntelligenceError,
    fetch_website_summary,
)
from app.services import ai_models

logger = logging.getLogger("auto_interview.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

# ── Brute-force lockout ───────────────────────────────────────────────
# Rate limiting throttles per-IP; this throttles per-ACCOUNT, so slow
# credential-stuffing across many IPs still locks the target account.
LOCKOUT_THRESHOLD = 5
LOCKOUT_MINUTES = 15


def _raise_if_locked(company: Company) -> None:
    if company.locked_until and company.locked_until > datetime.utcnow():
        remaining = int((company.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many failed sign-in attempts. "
                f"Try again in {remaining} minute{'s' if remaining != 1 else ''}."
            ),
        )


def _register_auth_failure(db: Session, company: Company) -> None:
    company.failed_login_attempts = (company.failed_login_attempts or 0) + 1
    if company.failed_login_attempts >= LOCKOUT_THRESHOLD:
        company.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        company.failed_login_attempts = 0
        logger.warning("Account locked after failed attempts: %s", company.email)
    db.commit()


def _register_auth_success(db: Session, company: Company) -> None:
    if company.failed_login_attempts or company.locked_until:
        company.failed_login_attempts = 0
        company.locked_until = None
        db.commit()


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def signup(request: Request, body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    # Fraud floor — canonicalize email so +tag aliases and gmail dot-
    # variants don't farm free credits. ``alice+study1@gmail.com`` and
    # ``a.lice@gmail.com`` both collapse to ``alice@gmail.com`` for the
    # uniqueness check. Stored email is the canonical form.
    from app.services.email_normalization import canonicalize_email
    from app.services.signup_prefetch import (
        extract_domain,
        is_disposable_email_domain,
    )

    canonical_email = canonicalize_email(body.email)
    if not canonical_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please enter a valid email address.",
        )

    # Block known disposable / throwaway-mail providers — they're the
    # primary vector for multi-account farming.
    if is_disposable_email_domain(extract_domain(canonical_email)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "We can't accept disposable email addresses. Please use "
                "your work or personal email."
            ),
        )

    existing = (
        db.query(Company)
        .filter(Company.email == canonical_email)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Try signing in instead.",
        )

    require_acceptable_password(body.password)

    # Resolve plan selection from the landing page.
    # All new accounts start on "starter" tier. The credits-based trial
    # (3 free interview credits) is bootstrapped on onboarding completion
    # via bootstrap_trial_subscription() — no calendar-based trial_ends_at.
    requested_plan = (body.plan or "").strip().lower()
    tier = "free" if requested_plan == "free" else "starter"

    # Honour the UI locale from the landing page (falls back to "fr" for
    # historical reasons — the model default). Anything other than en/fr
    # normalises to "en" inside the email service.
    signup_lang = (body.preferred_language or "").lower().strip()
    if signup_lang not in ("en", "fr"):
        signup_lang = "fr"

    company = Company(
        name=body.name.strip(),
        email=canonical_email,
        password_hash=hash_password(body.password),
        subscription_tier=tier,
        trial_ends_at=None,
        preferred_language=signup_lang,
        first_name=body.first_name.strip() if body.first_name else None,
        last_name=body.last_name.strip() if body.last_name else None,
    )
    db.add(company)
    db.commit()
    db.refresh(company)

    logger.info("New company signup: %s", company.email)
    emit_event("signup", company=company, plan_requested=requested_plan or "starter")

    # W2.5 — fire the domain pre-fetch in a background thread so the
    # copilot walks into the very first /welcome turn already knowing
    # what the company does. Never blocks signup, never fails the
    # caller. Skips freemail domains automatically.
    try:
        from app.services.signup_prefetch import prefetch_company_intel
        prefetch_company_intel(
            company_id=company.id,
            email=company.email,
            language=signup_lang,
        )
    except Exception:
        # Defence-in-depth — prefetch_company_intel already swallows,
        # but the import itself shouldn't be allowed to break signup.
        logger.exception("signup prefetch failed to schedule")

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

    # Send ONLY the verification email at signup — not a separate welcome.
    # We used to send both immediately and users confused the "Your account
    # is ready" welcome mail with an action email, missed the verify step,
    # and then the verify mail (which landed in spam) never got clicked.
    # The welcome now fires from ``verify_email`` right after the address
    # is confirmed, which is both cleaner (one action at a time) and better
    # for deliverability (fewer messages in the first 30 seconds = lower
    # engagement-based spam risk).
    verify_url = f"{settings.APP_BASE_URL}/verify-email?token={verification_token.token}"
    # Greet the *person* (first name), not the company — "Welcome, Marie"
    # reads far more human than "Welcome, Acme Research". Fall back to the
    # company name only if no first name was captured at signup.
    greet_name = (company.first_name or "").strip() or company.name
    send_verification_email(
        company.email, greet_name, verify_url, lang=company.preferred_language
    )

    return TokenResponse(
        access_token=create_access_token(company_token_claims(company)),
        refresh_token=create_refresh_token(company_token_claims(company)),
    )


@router.post("/login")
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    """Password step. Returns session tokens directly, or — when the account
    has 2FA enabled — ``{"requires_2fa": true, "pending_token": ...}`` to be
    exchanged at POST /auth/login/2fa."""
    company = db.query(Company).filter(Company.email == body.email.lower().strip()).first()
    if company is not None:
        _raise_if_locked(company)
    if not company or not company.password_hash or not verify_password(body.password, company.password_hash):
        # Google-only accounts (no password_hash) hit this branch — same
        # generic message as a wrong password to avoid leaking which
        # identity providers a given email is registered with.
        if company is not None and company.password_hash:
            _register_auth_failure(db, company)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if company.suspended_at is not None:
        reason = company.suspension_reason or "Contact support for details."
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account suspended: {reason}",
        )

    _register_auth_success(db, company)

    if company.totp_enabled:
        return {"requires_2fa": True, "pending_token": create_2fa_pending_token(company.id)}

    logger.info("Login: %s", company.email)
    return TokenResponse(
        access_token=create_access_token(company_token_claims(company)),
        refresh_token=create_refresh_token(company_token_claims(company)),
    )


class TwoFactorLoginRequest(BaseModel):
    pending_token: str
    code: str


@router.post("/login/2fa", response_model=TokenResponse)
@limiter.limit("10/minute")
def login_2fa(request: Request, body: TwoFactorLoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Second factor: exchange the pending token + a TOTP or backup code
    for real session tokens."""
    payload = decode_2fa_pending_token(body.pending_token)
    company = db.query(Company).filter(Company.id == payload.get("sub")).first()
    if not company or not company.totp_enabled or not company.totp_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA session")
    _raise_if_locked(company)

    if not verify_totp_code(company.totp_secret, body.code):
        remaining_codes = consume_backup_code(company.totp_backup_codes, body.code)
        if remaining_codes is None:
            _register_auth_failure(db, company)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid verification code",
            )
        company.totp_backup_codes = remaining_codes
        logger.info("2FA backup code used: %s", company.email)

    _register_auth_success(db, company)
    db.commit()
    logger.info("Login (2FA): %s", company.email)
    return TokenResponse(
        access_token=create_access_token(company_token_claims(company)),
        refresh_token=create_refresh_token(company_token_claims(company)),
    )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
def refresh_token(request: Request, body: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    payload = decode_refresh_token(body.refresh_token)
    company_id: str | None = payload.get("sub")
    if not company_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found")
    check_token_version(payload, company)
    if company.suspended_at is not None:
        reason = company.suspension_reason or "Contact support for details."
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account suspended: {reason}",
        )
    return TokenResponse(
        access_token=create_access_token(company_token_claims(company)),
        refresh_token=create_refresh_token(company_token_claims(company)),
    )


@router.post("/logout-all")
def logout_all(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Revoke every outstanding session for this account (including this
    one) by bumping token_version. The caller should drop its local tokens
    and sign in again."""
    company.token_version = (company.token_version or 0) + 1
    db.commit()
    logger.info("Logout-all (token_version bump) for %s", company.email)
    return {"message": "All sessions have been signed out."}


# ââ Email Verification ââââââââââââââââââââââââââââââââââââââââââââââââ

@router.post("/verify-email")
@limiter.limit("10/minute")
def verify_email(request: Request, token: str, db: Session = Depends(get_db)):
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

    already_verified = company.email_verified
    company.email_verified = True
    token_row.used = True
    db.commit()

    logger.info("Email verified for %s", company.email)

    # NOTE: the welcome email is intentionally NOT sent here anymore.
    # It now fires from POST /auth/onboarding once the user has completed
    # the 4-step wizard, so it can embed the personalised research brief
    # (Claude-generated from their role + company + use cases). Sending a
    # generic "Welcome" here would arrive empty-handed and compete with
    # the real, brief-carrying welcome that lands a few minutes later.
    _ = already_verified  # retained for potential future analytics hook

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
    # Greet the *person* (first name), not the company — "Welcome, Marie"
    # reads far more human than "Welcome, Acme Research". Fall back to the
    # company name only if no first name was captured at signup.
    greet_name = (company.first_name or "").strip() or company.name
    send_verification_email(
        company.email, greet_name, verify_url, lang=company.preferred_language
    )

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
        send_password_reset(company.email, reset_url, lang=company.preferred_language)
        logger.info("Password reset requested for %s", company.email)
    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/password-reset/confirm")
def confirm_password_reset(body: PasswordResetConfirm, db: Session = Depends(get_db)):
    require_acceptable_password(body.new_password)
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
    # A reset usually means the old credentials can't be trusted — revoke
    # every outstanding session, and clear any brute-force lockout so the
    # legitimate owner isn't left waiting out an attacker's lock.
    company.token_version = (company.token_version or 0) + 1
    company.failed_login_attempts = 0
    company.locked_until = None
    token_row.used = True
    db.commit()
    logger.info("Password reset completed for %s", company.email)
    return {"message": "Password updated successfully"}


# ââ Profile & Onboarding ââââââââââââââââââââââââââââââââââââââââââââââââ

@router.get("/me", response_model=CompanyResponse)
def get_me(company: Company = Depends(get_current_company)) -> CompanyResponse:
    resp = CompanyResponse.model_validate(company)
    resp.is_impersonation = getattr(company, "_is_impersonation", False)
    resp.impersonation_admin = getattr(company, "_impersonation_admin", None)
    return resp


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


@router.get("/branding-defaults")
def get_branding_defaults(
    company: Company = Depends(get_current_company),
) -> dict:
    """Workspace-level branding defaults prefilled into every new study."""
    return {"defaults": company.branding_defaults_dict}


@router.put("/branding-defaults")
def put_branding_defaults(
    body: BrandingDefaultsPayload,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
) -> dict:
    """Save the workspace branding defaults (validated like project branding).

    Theming values (branded mode / colour / font) require the same
    ``custom_branding`` entitlement as setting them on a study.
    """
    from app.services.billing_service import workspace_has_feature

    wants_theming = (
        body.branding_mode == "branded"
        or body.brand_primary_color is not None
        or body.brand_font is not None
    )
    if wants_theming and not workspace_has_feature(db, company, "custom_branding"):
        raise HTTPException(status_code=403, detail="custom_branding_required")

    defaults = {
        key: value
        for key, value in {
            "branding_mode": body.branding_mode,
            "brand_primary_color": body.brand_primary_color,
            "brand_font": body.brand_font,
            "researcher_name": (body.researcher_name or "").strip() or None,
            "researcher_logo_url": (body.researcher_logo_url or "").strip() or None,
            "privacy_policy_url": (body.privacy_policy_url or "").strip() or None,
        }.items()
        if value is not None
    }
    company.branding_defaults = json.dumps(defaults) if defaults else None
    db.commit()
    return {"defaults": defaults}


@router.patch("/me/priority", response_model=CompanyResponse)
def update_current_priority(
    body: PriorityUpdate,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Update the researcher's current top-of-mind priority.

    The Dashboard shows a soft prompt every ~30 days asking "what's most
    important for you to learn right now?". The answer is stored on the
    Company record so we can (a) show it as a reminder next time they visit
    and (b) eventually feed it into the recommended-studies ranking.

    Pass ``current_priority=None`` or an empty string to clear.
    """
    value = body.current_priority
    if value is not None:
        value = value.strip()
        if not value:
            value = None
        elif len(value) > 280:
            value = value[:280]
    company.current_priority = value
    company.current_priority_updated_at = datetime.utcnow()
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
    primary_country = result.get("primary_country")

    company.website_url = url
    company.business_summary = summary
    if industry:
        company.industry = industry
    # Persist detected primary market so it survives a page reload and so
    # the AccountSettings / email flows have a default to work with. The
    # frontend also preselects the matching chip in the onboarding UI.
    if primary_country:
        company.primary_region = primary_country
    db.commit()

    logger.info(
        "Website intel generated for %s: %s (industry=%s, country=%s)",
        company.email,
        url,
        industry,
        primary_country,
    )
    return {
        "business_summary": summary,
        "industry": industry,
        "primary_country": primary_country,
    }


def _apply_onboarding_fields(company: Company, body: OnboardingProfileRequest) -> None:
    """Persist any onboarding fields provided in the request.

    Single source of truth for PATCH /onboarding (intermediate save) and
    POST /onboarding (complete). Empty-string is treated as "clear this
    field" for text fields; missing/None leaves the existing value alone.
    """
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
    if body.preferred_language:
        normalized = body.preferred_language.strip().lower()[:2]
        if normalized in ("en", "fr"):
            company.preferred_language = normalized

    # Business context
    if body.value_proposition is not None:
        company.value_proposition = body.value_proposition
    if body.primary_competitors is not None:
        company.primary_competitors = body.primary_competitors
    if body.product_stage is not None:
        company.product_stage = body.product_stage
    if body.customer_type is not None:
        company.customer_type = body.customer_type

    # Qualification signals
    if body.interviews_per_month_target is not None:
        company.interviews_per_month_target = body.interviews_per_month_target
    if body.current_tool is not None:
        company.current_tool = body.current_tool
    if body.decision_role is not None:
        company.decision_role = body.decision_role
    if body.referral_source is not None:
        company.referral_source = body.referral_source

    # Onboarding redesign — personal identity + recap
    if body.first_name is not None:
        company.first_name = body.first_name.strip() or None
    if body.last_name is not None:
        company.last_name = body.last_name.strip() or None
    if body.occupation_description is not None:
        company.occupation_description = body.occupation_description
    if body.selected_use_cases is not None:
        company.selected_use_cases = body.selected_use_cases
    if body.onboarding_recap is not None:
        company.onboarding_recap = body.onboarding_recap
    if body.study_readiness is not None:
        company.study_readiness = body.study_readiness


@router.patch("/onboarding")
def save_onboarding_profile(
    body: OnboardingProfileRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Save company profile details during onboarding (intermediate save, doesn't mark complete)."""
    name_before = (company.name or "").strip()
    _apply_onboarding_fields(company, body)
    db.commit()
    logger.info("Onboarding profile saved for %s", company.email)

    # Re-run business-context backfill whenever the typed company name
    # materially changes — not just when business_summary is empty.
    # Why: a user signing up with corino@legalstart.fr triggers a
    # domain prefetch that populates business_summary with Legalstart's
    # description. If they then type "Acme Corp" in the wizard, the
    # summary becomes stale. We re-run so the summary always matches
    # the typed name. Conservative: skip when the change is trivial
    # (case-only or whitespace-only) to avoid spurious Haiku calls.
    name_after = (company.name or "").strip()
    if (
        name_after
        and name_after.lower() != name_before.lower()
        and len(name_after) >= 2
    ):
        _schedule_company_name_backfill(company.id)

    return CompanyResponse.model_validate(company)


def _schedule_company_name_backfill(company_id: str) -> None:
    """Background-thread Haiku call to populate business_summary +
    industry from the typed company name. Daemonised — swallows every
    error path, never blocks the wizard."""
    import threading

    from app.database import SessionLocal

    def run() -> None:
        bg_db = SessionLocal()
        try:
            from app.models.company import Company as _Company
            from app.services.company_name_lookup import (
                backfill_business_from_name,
            )

            c = (
                bg_db.query(_Company)
                .filter(_Company.id == company_id)
                .first()
            )
            if c is None:
                return
            # Only force-overwrite if no domain-prefetched summary exists.
            # Domain-prefetch is higher quality (from the actual website)
            # than a Haiku guess from a typed company name.
            has_domain_summary = bool((c.business_summary or "").strip())
            if backfill_business_from_name(
                c, force=not has_domain_summary, db=bg_db
            ):
                bg_db.commit()
                logger.info(
                    "Backfilled business context for %s from typed name '%s'",
                    c.email,
                    c.name,
                )
        except Exception:  # noqa: BLE001 — swallow, this is fire-and-forget
            logger.exception("company-name backfill thread failed")
        finally:
            bg_db.close()

    threading.Thread(target=run, daemon=True).start()


# ── Onboarding suggestions (Haiku) ──────────────────────────────────────────

_FALLBACK_USE_CASES_EN = [
    "Why users drop off",
    "What drives loyalty and repeat use",
    "How people choose between options",
    "Where the experience creates friction",
    "What customers value most",
]
_FALLBACK_USE_CASES_FR = [
    "Pourquoi les utilisateurs décrochent",
    "Ce qui favorise la fidélité",
    "Comment les gens font leur choix",
    "Où l'expérience crée de la friction",
    "Ce que les clients valorisent le plus",
]


@router.get("/onboarding/suggestions")
@limiter.limit("10/minute")
def get_onboarding_suggestions(
    request: Request,
    model: str = "sonnet",
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Return AI-suggested use cases and a profile summary for onboarding step 3.

    Reads the current Company state (role, company_size, business_summary,
    industry) and calls Claude to generate personalised suggestions.
    Degrades gracefully when data is sparse or the API is unavailable.

    ``model`` selects the tier: ``sonnet`` (default) for goal-driven
    generation where the extra reasoning anchors themes on the user's own
    words, or ``haiku`` for the fast role-only path (the wizard sends this
    when the user skipped the free-text goal). Any other value falls back
    to Sonnet.
    """
    lang = (company.preferred_language or "en").strip().lower()[:2]
    fallback_cases = _FALLBACK_USE_CASES_FR if lang == "fr" else _FALLBACK_USE_CASES_EN

    has_context = bool((company.business_summary or "").strip())
    role = (company.role or "").strip()
    size = (company.company_size or "").strip()
    industry = (company.industry or "").strip()
    summary = (company.business_summary or "").strip()
    name = (company.name or "").strip()
    goals = (company.goals_freeform or "").strip()

    if not role and not has_context and not goals:
        return {
            "use_cases": fallback_cases,
            "profile_summary": None,
            "business_summary": summary or None,
        }

    try:
        from app.services._clients import get_anthropic_client
        from app.config import settings as _settings

        if not _settings.ANTHROPIC_API_KEY:
            raise ValueError("no key")

        client = get_anthropic_client(30.0)

        context_parts = []
        if name:
            context_parts.append(f"Company: {name}")
        if role:
            context_parts.append(f"Role: {role}")
        if size:
            context_parts.append(f"Team size: {size}")
        if industry:
            context_parts.append(f"Industry: {industry}")
        if summary:
            context_parts.append(f"About the company: {summary}")
        if goals:
            context_parts.append(
                f"In their own words, what they're working on / want to learn: {goals}"
            )

        context_block = "\n".join(context_parts)

        output_lang = "French" if lang == "fr" else "English"

        model_id = ai_models.haiku() if model == "haiku" else ai_models.sonnet()

        resp = client.messages.create(
            model=model_id,
            max_tokens=400,
            messages=[{
                "role": "user",
                "content": (
                    f"Based on this user profile:\n{context_block}\n\n"
                    f"1. Suggest 4-5 research studies THIS SPECIFIC PERSON would "
                    f"actually want to run — concrete and personalised to their "
                    f"role, their company, what the company does, and (most "
                    f"important) what they said they're working on. Do NOT return "
                    f"generic textbook themes that could fit any company; use the "
                    f"real details you were given. When the profile names a "
                    f"product, market, customer type, or programme (e.g. a loyalty "
                    f"scheme, a specific app, a segment), it is GOOD to reference "
                    f"it so the study reads as tailor-made — e.g. for an airline "
                    f"loyalty lead: 'What keeps frequent flyers loyal', 'Why "
                    f"members stop redeeming miles'. Each suggestion is a clear "
                    f"research objective the user instantly recognises as theirs. "
                    f"HARD LIMITS: 8 words maximum per suggestion. If the profile "
                    f"includes an 'In their own words' line, at least half the "
                    f"suggestions must be anchored directly on what they said they "
                    f"want to learn. Rephrase their intent cleanly in proper, "
                    f"typo-free wording — never echo their raw text back. Do NOT "
                    f"use commas inside a suggestion. When writing in French, "
                    f"follow French typography (a space before ? ! : ;).\n"
                    f"2. Write a warm 1-2 sentence summary addressed DIRECTLY to "
                    f"the user in the second person (\"You…\" / \"Vous…\"), "
                    f"confirming what you understand about their role, their "
                    f"company, and — when they shared it — what they're working on. "
                    f"Restate their goal in clean prose; do NOT quote their raw "
                    f"words or reproduce any typos. Never describe them in the "
                    f"third person (never \"This person\" / \"Cette personne\").\n\n"
                    f"Output ONLY valid JSON in {output_lang}:\n"
                    f'{{"use_cases": ["...", "..."], "profile_summary": "..."}}'
                ),
            }],
        )

        from app.services.usage_logger import log_claude_usage

        log_claude_usage(
            db, resp, "onboarding_suggestions", company_id=company.id
        )

        import json
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)

        use_cases = data.get("use_cases", fallback_cases)
        if not isinstance(use_cases, list) or len(use_cases) < 2:
            use_cases = fallback_cases
        profile_summary = data.get("profile_summary")
        if not isinstance(profile_summary, str):
            profile_summary = None

        return {
            "use_cases": use_cases[:6],
            "profile_summary": profile_summary,
            "business_summary": summary or None,
        }

    except Exception:
        logger.warning("Onboarding suggestions Haiku call failed", exc_info=True)
        return {
            "use_cases": fallback_cases,
            "profile_summary": None,
            "business_summary": summary or None,
        }


@router.post("/onboarding")
def complete_onboarding(
    body: OnboardingProfileRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Save company profile details and mark onboarding as complete."""
    _apply_onboarding_fields(company, body)

    # Classify free-form goals into stable buckets for analytics / sales.
    # Best-effort: if the classifier fails (API down, no key) we just skip.
    if body.goals_freeform:
        try:
            from app.services.goals_classifier import classify_goals
            company.goals_classification = classify_goals(
                body.goals_freeform, db=db, company_id=company.id
            )
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to classify goals for %s", company.email)

    company.onboarding_completed = True
    db.commit()
    emit_event("onboarding_completed", company=company)

    # Place the new account on the credits-based trial plan. Idempotent —
    # subsequent onboarding completions (replays, reset flows) no-op when
    # the workspace is already trialing or on a paid plan.
    try:
        from app.services.billing_service import bootstrap_trial_subscription
        bootstrap_trial_subscription(db, company)
    except Exception:  # pragma: no cover — never block onboarding on billing
        logger.exception("Trial bootstrap failed for %s; legacy backfill remains in place", company.email)

    # Seed the showcase demo project and send the personalised welcome email
    # in a background thread so the onboarding response returns immediately.
    # Both operations are idempotent / best-effort — failures are logged but
    # never surfaced to the user.
    if company.demo_seeded_at is None:
        _company_id = company.id
        _company_snapshot = {
            "email": company.email,
            "name": company.name,
            "first_name": company.first_name,
            "last_name": company.last_name,
            "role": company.role,
            "occupation_description": company.occupation_description,
            "industry": company.industry,
            "selected_use_cases": company.selected_use_cases,
            "preferred_language": company.preferred_language,
            "slack_webhook_url": company.slack_webhook_url,
        }

        def _background_post_onboarding(company_id: str, snapshot: dict) -> None:
            from app.database import SessionLocal
            from app.models.company import Company as _Company

            # ── 1. Demo seeder + Slack notification (need a live DB session) ──
            db_bg = SessionLocal()
            try:
                bg_company = db_bg.query(_Company).filter(_Company.id == company_id).first()
                if bg_company:
                    if bg_company.demo_seeded_at is None:
                        # The conversational onboarding may have already
                        # created the researcher's real first study. Only
                        # seed the read-only demo when there's nothing real
                        # yet — the demo is now a fallback, not the default.
                        from app.models.project import Project as _Project
                        has_real_study = (
                            db_bg.query(_Project)
                            .filter(
                                _Project.company_id == company_id,
                                _Project.is_demo.is_(False),
                            )
                            .first()
                            is not None
                        )
                        if not has_real_study:
                            seed_demo_project(db_bg, company_id)
                        bg_company.demo_seeded_at = datetime.utcnow()
                        db_bg.commit()

                    # Use the freshly-loaded ORM object so all fields are available.
                    try:
                        from app.services.sales_notify import notify_new_signup
                        notify_new_signup(bg_company)
                    except Exception:  # pragma: no cover - defensive
                        logger.exception("Background sales notify failed for %s", snapshot["email"])
            except Exception:  # pragma: no cover - defensive
                db_bg.rollback()
                logger.exception("Background demo seeder failed for %s", snapshot["email"])
            finally:
                db_bg.close()

            # ── 2. Personalised welcome email (may call Claude) ──────────────
            try:
                import json as _json
                use_cases_list: list[str] | None = None
                raw_uc = snapshot.get("selected_use_cases")
                if raw_uc:
                    try:
                        use_cases_list = _json.loads(raw_uc)
                    except (ValueError, TypeError):
                        use_cases_list = None

                send_personalized_welcome(
                    to=snapshot["email"],
                    name=snapshot["name"],
                    first_name=snapshot.get("first_name"),
                    last_name=snapshot.get("last_name"),
                    company_name=snapshot["name"],
                    role_title=snapshot.get("role"),
                    occupation_description=snapshot.get("occupation_description"),
                    industry=snapshot.get("industry"),
                    selected_use_cases=use_cases_list,
                    lang=snapshot.get("preferred_language") or "en",
                    company_id=company_id,
                )
            except Exception:  # pragma: no cover - defensive
                logger.exception("Background welcome email failed for %s", snapshot["email"])

        t = threading.Thread(
            target=_background_post_onboarding,
            args=(_company_id, _company_snapshot),
            daemon=True,
        )
        t.start()
        logger.info("Demo seeder + welcome email dispatched to background for %s", company.email)
    else:
        # Already seeded — just fire the Slack notification (fast, no Claude).
        try:
            from app.services.sales_notify import notify_new_signup
            notify_new_signup(company)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Failed to send sales notification for %s", company.email)

    logger.info("Onboarding completed for %s", company.email)
    return CompanyResponse.model_validate(company)


@router.post("/change-password")
@limiter.limit("5/minute")
def change_password(
    request: Request,
    body: ChangePasswordRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Change password â requires current password verification."""
    if not company.password_hash or not verify_password(body.current_password, company.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    require_acceptable_password(body.new_password)
    company.password_hash = hash_password(body.new_password)
    # Revoke every other session; hand fresh tokens back so THIS session
    # survives the token_version bump.
    company.token_version = (company.token_version or 0) + 1
    db.commit()
    db.refresh(company)
    logger.info("Password changed for %s", company.email)
    return {
        "message": "Password updated successfully",
        "access_token": create_access_token(company_token_claims(company)),
        "refresh_token": create_refresh_token(company_token_claims(company)),
    }


class DeleteAccountRequest(BaseModel):
    password: Optional[str] = None
    confirm: Optional[str] = None


@router.post("/delete-account", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/minute")
def delete_account(
    request: Request,
    body: DeleteAccountRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
) -> None:
    """Self-serve GDPR account deletion — erases the company and all its data.

    Password accounts must supply the correct current password; OAuth-only
    accounts (no password hash) must send confirm == "DELETE" instead.
    """
    from app.services.deletion import delete_company_data

    if company.password_hash:
        if not body.password or not verify_password(body.password, company.password_hash):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Password is incorrect",
            )
    else:
        if body.confirm != "DELETE":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='Type "DELETE" to confirm account deletion',
            )

    logger.warning(
        "ACCOUNT_SELF_DELETION: company_id=%s email=%s name=%s timestamp=%s",
        company.id, company.email, company.name,
        datetime.now(timezone.utc).isoformat(),
    )
    summary = delete_company_data(db, company, delete_files=True)
    logger.warning("ACCOUNT_SELF_DELETION_DONE: %s", summary)


# ── Two-factor authentication (TOTP) ──────────────────────────────────


class TwoFactorEnableRequest(BaseModel):
    code: str


class TwoFactorDisableRequest(BaseModel):
    code: str
    password: Optional[str] = None


@router.post("/2fa/setup")
@limiter.limit("5/minute")
def two_factor_setup(
    request: Request,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Start TOTP enrolment: generate a secret and return the otpauth URI.
    2FA does not enforce until /2fa/enable confirms a valid code."""
    if company.totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Two-factor authentication is already enabled.",
        )
    secret = generate_totp_secret()
    company.totp_secret = secret
    db.commit()
    return {
        "secret": secret,
        "otpauth_url": totp_provisioning_uri(secret, company.email),
    }


@router.post("/2fa/enable")
@limiter.limit("10/minute")
def two_factor_enable(
    request: Request,
    body: TwoFactorEnableRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Confirm enrolment with a code from the authenticator app. Returns
    the backup codes — shown exactly once, stored only as hashes."""
    if company.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already enabled.")
    if not company.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run setup first.")
    if not verify_totp_code(company.totp_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification code. Check your authenticator app and try again.",
        )
    backup_codes, hashed_json = generate_backup_codes()
    company.totp_enabled = True
    company.totp_backup_codes = hashed_json
    db.commit()
    logger.info("2FA enabled for %s", company.email)
    return {"message": "Two-factor authentication enabled", "backup_codes": backup_codes}


@router.post("/2fa/disable")
@limiter.limit("5/minute")
def two_factor_disable(
    request: Request,
    body: TwoFactorDisableRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Turn 2FA off. Requires a currently-valid TOTP or backup code, plus
    the account password when one exists (Google-only accounts skip it)."""
    if not company.totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled.")
    if company.password_hash:
        if not body.password or not verify_password(body.password, company.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )
    code_ok = verify_totp_code(company.totp_secret or "", body.code)
    if not code_ok:
        remaining = consume_backup_code(company.totp_backup_codes, body.code)
        if remaining is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code",
            )
    company.totp_enabled = False
    company.totp_secret = None
    company.totp_backup_codes = None
    db.commit()
    logger.info("2FA disabled for %s", company.email)
    return {"message": "Two-factor authentication disabled"}


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


# ── Google OAuth ──────────────────────────────────────────────────────
#
# Authorization-code flow:
#   1. Frontend calls GET /auth/google/login → returns Google's consent URL
#      (state is a short-lived signed JWT carrying CSRF nonce + post-login
#      redirect path + UI language).
#   2. User consents on Google → Google redirects back to
#      GET /auth/google/callback?code=...&state=... .
#   3. Backend exchanges the code for an id_token + access_token, fetches
#      userinfo, then creates or links the local Company. New accounts get
#      email_verified=True (Google has already verified the address) and
#      the same starter tier as password signups (credits trial bootstrapped
#      on onboarding completion).
#   4. Backend redirects to {APP_BASE_URL}/auth/google/finish with our JWT
#      access + refresh tokens in the URL fragment, plus the onboarded flag
#      so the frontend can route to /welcome vs /dashboard.

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


_FREEMAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "yahoo.fr", "yahoo.co.uk", "icloud.com", "me.com", "mac.com",
    "proton.me", "protonmail.com", "aol.com", "gmx.com", "gmx.fr",
    "free.fr", "orange.fr", "wanadoo.fr", "laposte.net", "sfr.fr",
}


def _company_name_from_email(email: str) -> str:
    """Friendlier placeholder workspace name than the user's full name.

    Google profiles ship a person's name, not a company name. Stuffing
    "Corino Fontana" into ``Company.name`` makes the onboarding read
    "Your role at Corino Fontana", which sounds wrong. We derive a
    workspace placeholder from the email domain instead — the user can
    (and should) override it on the onboarding "Your company" step.

    For corporate domains we capitalise the second-level label
    (``corino@qualipulse.com`` → "Qualipulse"). Free-mail domains
    (gmail, yahoo, …) carry no signal so we fall back to the local part
    of the address.
    """
    if "@" not in email:
        return email or "My workspace"
    local, _, domain = email.partition("@")
    domain = domain.lower().strip()
    if domain in _FREEMAIL_DOMAINS or not domain:
        return (local or "My workspace").capitalize()
    label = domain.split(".")[0]
    return label.capitalize() if label else (local or "My workspace").capitalize()


def _google_redirect_uri() -> str:
    """The redirect URI we register with Google + receive callbacks at.

    Configurable via ``GOOGLE_REDIRECT_URI`` so dev (FastAPI on :8000) and
    prod (api.qualipulse.com) can each use their own host. Falls back to a
    sensible default built off the request — but in practice Google requires
    an exact pre-registered match, so this should always be set explicitly.
    """
    return settings.GOOGLE_REDIRECT_URI.strip()


def _google_configured() -> bool:
    return bool(
        settings.GOOGLE_CLIENT_ID
        and settings.GOOGLE_CLIENT_SECRET
        and _google_redirect_uri()
    )


def _encode_oauth_state(payload: dict) -> str:
    """Sign the OAuth state blob with SECRET_KEY (CSRF + redirect carrier)."""
    to_encode = {
        **payload,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
        "nonce": secrets.token_urlsafe(16),
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def _decode_oauth_state(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state",
        ) from exc


@router.get("/google/login")
def google_login(
    request: Request,
    next: str = "/dashboard",
    lang: str = "",
):
    """Return the Google authorization URL the frontend should redirect to."""
    if not _google_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on this environment.",
        )

    # Whitelist the post-login path so an attacker can't open-redirect us
    # off-site through the state parameter.
    safe_next = next if next.startswith("/") and not next.startswith("//") else "/dashboard"
    safe_lang = lang.strip().lower()[:2] if lang else ""

    state = _encode_oauth_state({"next": safe_next, "lang": safe_lang})

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": _google_redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
        "state": state,
    }
    return {"authorize_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


def _redirect_to_frontend_with_error(error: str, next_path: str = "/login") -> RedirectResponse:
    target = f"{settings.APP_BASE_URL}{next_path}?google_error={error}"
    return RedirectResponse(url=target, status_code=302)


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    """Exchange Google's auth code → upsert account → bounce to frontend."""
    if not _google_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google sign-in is not configured on this environment.",
        )

    if error:
        # User clicked "Cancel" on Google's consent screen, etc.
        return _redirect_to_frontend_with_error(error)

    if not code or not state:
        return _redirect_to_frontend_with_error("missing_code")

    state_payload = _decode_oauth_state(state)
    next_path = state_payload.get("next") or "/dashboard"
    lang = state_payload.get("lang") or ""

    # Exchange the authorization code for tokens (server-to-server).
    try:
        with httpx.Client(timeout=10.0) as http:
            token_resp = http.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": _google_redirect_uri(),
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            if token_resp.status_code != 200:
                logger.warning(
                    "Google token exchange failed: %s %s",
                    token_resp.status_code,
                    token_resp.text[:200],
                )
                return _redirect_to_frontend_with_error("token_exchange_failed")
            tokens = token_resp.json()

            access_token_g = tokens.get("access_token")
            if not access_token_g:
                return _redirect_to_frontend_with_error("no_access_token")

            userinfo_resp = http.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token_g}"},
            )
            if userinfo_resp.status_code != 200:
                return _redirect_to_frontend_with_error("userinfo_failed")
            userinfo = userinfo_resp.json()
    except httpx.HTTPError:
        logger.exception("Network error talking to Google")
        return _redirect_to_frontend_with_error("network_error")

    google_sub = userinfo.get("sub")
    email = (userinfo.get("email") or "").lower().strip()
    email_verified_g = bool(userinfo.get("email_verified"))
    given_name = userinfo.get("given_name")
    family_name = userinfo.get("family_name")

    if not google_sub or not email:
        return _redirect_to_frontend_with_error("incomplete_profile")

    # Match by google_sub first (covers users who later changed email on
    # Google), then by email (covers existing password accounts linking
    # their Google identity for the first time). The email fallback is only
    # safe when Google attests it verified the address — otherwise anyone
    # who can create a Google account claiming a victim's email could take
    # over the victim's workspace.
    company = db.query(Company).filter(Company.google_sub == google_sub).first()
    if company is None:
        if not email_verified_g:
            return _redirect_to_frontend_with_error("email_unverified")
        company = db.query(Company).filter(Company.email == email).first()

    is_new_account = company is None

    if company is None:
        # Brand-new signup via Google — starts on starter tier, credits-based
        # trial bootstrapped on onboarding completion (no calendar trial).
        # Don't use Google's full name (e.g. "Corino Fontana") as the
        # workspace name — the onboarding wizard then says "Your role at
        # Corino Fontana" which is awkward. Derive a placeholder from the
        # email domain (corino@qualipulse.com → "Qualipulse"); the user
        # corrects it on the "Your company" onboarding step before any AI
        # prompts get grounded in the wrong name.
        signup_lang = lang if lang in ("en", "fr") else "en"
        company = Company(
            name=_company_name_from_email(email),
            email=email,
            password_hash=None,
            google_sub=google_sub,
            email_verified=email_verified_g,
            subscription_tier="starter",
            trial_ends_at=None,
            preferred_language=signup_lang,
            first_name=given_name,
            last_name=family_name,
        )
        db.add(company)
        db.commit()
        db.refresh(company)
        logger.info("New Google signup: %s", company.email)
    else:
        # Link Google to existing account (idempotent) and trust Google's
        # verified flag to mark the email as verified if it wasn't already.
        changed = False
        first_time_link = company.google_sub != google_sub
        if first_time_link:
            company.google_sub = google_sub
            changed = True
            # Security notice on first-time linking to a pre-existing
            # password account: the legitimate owner learns immediately if
            # someone else just attached a Google identity to their login.
            if company.password_hash:
                try:
                    from app.services.email import send_google_link_notice
                    send_google_link_notice(
                        company.email, lang=company.preferred_language
                    )
                except Exception:  # pragma: no cover — never block login on email
                    logger.exception("Google-link notice failed for %s", company.email)
        if email_verified_g and not company.email_verified:
            company.email_verified = True
            changed = True
        if not company.first_name and given_name:
            company.first_name = given_name
            changed = True
        if not company.last_name and family_name:
            company.last_name = family_name
            changed = True
        if changed:
            db.commit()
            db.refresh(company)
        logger.info("Google login: %s (linked=%s)", company.email, changed)

    access = create_access_token(company_token_claims(company))
    refresh = create_refresh_token(company_token_claims(company))

    # Send tokens back via URL fragment so they don't appear in server logs
    # / Referer headers. The frontend's /auth/google/finish route reads
    # window.location.hash, stores tokens, then routes to next_path or
    # /welcome based on the onboarded flag.
    frag_params = urlencode({
        "access_token": access,
        "refresh_token": refresh,
        "onboarded": "1" if company.onboarding_completed else "0",
        "is_new": "1" if is_new_account else "0",
        "next": next_path,
    })
    return RedirectResponse(
        url=f"{settings.APP_BASE_URL}/auth/google/finish#{frag_params}",
        status_code=302,
    )


class NewsletterSubscribe(BaseModel):
    email: str


@router.post("/newsletter")
@limiter.limit("5/minute")
def subscribe_newsletter(request: Request, body: NewsletterSubscribe):
    """Subscribe to newsletter â just sends a welcome email for now."""
    # Pick language from Accept-Language (the newsletter form is anonymous,
    # so we have no user record to read preferred_language from).
    accept_lang = (request.headers.get("accept-language") or "").lower()
    lang = "fr" if accept_lang.startswith("fr") else "en"
    send_newsletter_welcome(body.email.lower().strip(), lang=lang)
    logger.info("Newsletter subscription: %s (lang=%s)", body.email, lang)
    return {"message": "Subscribed successfully"}
