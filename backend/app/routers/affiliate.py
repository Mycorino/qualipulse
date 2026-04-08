import logging
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.limiter import limiter
from app.models.company import Company
from app.models.affiliate import Affiliate, AffiliateReferral, AffiliatePayout
from app.services.auth import create_access_token

logger = logging.getLogger("auto_interview.affiliate")
router = APIRouter(prefix="/affiliates", tags=["affiliates"])


# ââ Schemas ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ


class AffiliateApplyRequest(BaseModel):
    name: str
    email: EmailStr
    code: str
    website: str | None = None
    how_they_found_us: str | None = None


class AffiliateLoginRequest(BaseModel):
    email: EmailStr
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AffiliateStatsResponse(BaseModel):
    id: str
    name: str
    email: str
    code: str
    status: str
    commission_pct: float
    total_earned: float
    total_paid: float
    payout_threshold: float
    signups: int
    conversions: int
    pending_earnings: float
    referral_link: str


class AffiliateReferralResponse(BaseModel):
    id: str
    referred_company_email: str
    status: str
    commission_amount: float | None
    signed_up_at: str
    converted_at: str | None


class AdminAffiliateResponse(BaseModel):
    id: str
    name: str
    email: str
    code: str
    status: str
    commission_pct: float
    total_earned: float
    total_paid: float
    signups: int
    conversions: int
    created_at: str


class AdminPayoutRequest(BaseModel):
    amount: float
    notes: str | None = None


# ââ Helpers ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ


def _validate_affiliate_code(code: str) -> str:
    """Validate and normalize affiliate code (kebab-case)."""
    code = code.strip().lower()
    # Only alphanumeric, hyphens, underscores
    if not re.match(r"^[a-z0-9_-]{3,50}$", code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Code must be 3-50 characters, lowercase alphanumeric, hyphens, or underscores.",
        )
    return code


def _get_admin_key(x_admin_key: str | None = Header(None)) -> str:
    """Verify admin key from header."""
    if not x_admin_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Admin-Key header",
        )
    if x_admin_key != settings.ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
        )
    return x_admin_key


def _get_affiliate_from_jwt(
    credentials: str,
    db: Session,
) -> Affiliate:
    """Extract affiliate_id from JWT and fetch affiliate."""
    from app.services.auth import decode_access_token

    payload = decode_access_token(credentials)
    sub: str | None = payload.get("sub")
    if not sub or not sub.startswith("affiliate:"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid affiliate token",
        )
    affiliate_id = sub[9:]  # Remove "affiliate:" prefix
    affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()
    if not affiliate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Affiliate not found",
        )
    return affiliate


# ââ Public endpoints ââââââââââââââââââââââââââââââââââââââââââââââââââââââ


@router.post("/apply", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def apply_for_affiliate(
    request: Request,
    body: AffiliateApplyRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Public endpoint: apply to become an affiliate."""
    # Check if email already exists
    existing = db.query(Affiliate).filter(Affiliate.email == body.email.lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An affiliate account with this email already exists.",
        )

    # Validate and normalize code
    code = _validate_affiliate_code(body.code)

    # Check if code is already taken
    existing_code = db.query(Affiliate).filter(Affiliate.code == code).first()
    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This affiliate code is already taken.",
        )

    # Create affiliate with pending status
    affiliate = Affiliate(
        name=body.name.strip(),
        email=body.email.lower(),
        code=code,
        website=body.website.strip() if body.website else None,
        how_they_found_us=body.how_they_found_us.strip() if body.how_they_found_us else None,
        status="pending",
    )
    db.add(affiliate)
    db.commit()
    db.refresh(affiliate)

    logger.info("New affiliate application: %s (%s)", affiliate.email, code)
    return {
        "message": "Application received. We'll review and get back to you within 2-3 business days.",
        "affiliate_id": affiliate.id,
    }


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def affiliate_login(
    request: Request,
    body: AffiliateLoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Affiliate login: email + code."""
    affiliate = db.query(Affiliate).filter(
        Affiliate.email == body.email.lower(),
        Affiliate.code == _validate_affiliate_code(body.code),
    ).first()

    if not affiliate:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or affiliate code.",
        )

    if affiliate.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Your affiliate account is {affiliate.status}. Contact support.",
        )

    logger.info("Affiliate login: %s", affiliate.email)
    return TokenResponse(
        access_token=create_access_token({"sub": f"affiliate:{affiliate.id}"})
    )


# ââ Authenticated affiliate endpoints ââââââââââââââââââââââââââââââââââââââ


def get_current_affiliate(
    credentials: str = Header(None),
    db: Session = Depends(get_db),
) -> Affiliate:
    """Dependency: extract affiliate from JWT."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )
    if credentials.startswith("Bearer "):
        credentials = credentials[7:]
    return _get_affiliate_from_jwt(credentials, db)


@router.get("/me", response_model=AffiliateStatsResponse)
def get_affiliate_stats(
    affiliate: Affiliate = Depends(get_current_affiliate),
    db: Session = Depends(get_db),
) -> AffiliateStatsResponse:
    """Get affiliate stats and earnings."""
    # Count signups and conversions
    referrals = db.query(AffiliateReferral).filter(
        AffiliateReferral.affiliate_id == affiliate.id
    ).all()

    signups = len(referrals)
    conversions = len([r for r in referrals if r.status == "converted"])
    pending_earnings = affiliate.total_earned - affiliate.total_paid

    return AffiliateStatsResponse(
        id=affiliate.id,
        name=affiliate.name,
        email=affiliate.email,
        code=affiliate.code,
        status=affiliate.status,
        commission_pct=affiliate.commission_pct,
        total_earned=affiliate.total_earned,
        total_paid=affiliate.total_paid,
        payout_threshold=affiliate.payout_threshold,
        signups=signups,
        conversions=conversions,
        pending_earnings=pending_earnings,
        referral_link=f"https://app.qualipulse.com/?ref={affiliate.code}",
    )


@router.get("/me/link")
def get_affiliate_link(affiliate: Affiliate = Depends(get_current_affiliate)) -> dict:
    """Get shareable referral link."""
    return {
        "referral_link": f"https://app.qualipulse.com/?ref={affiliate.code}",
        "code": affiliate.code,
    }


@router.get("/me/referrals")
def get_affiliate_referrals(
    affiliate: Affiliate = Depends(get_current_affiliate),
    db: Session = Depends(get_db),
) -> dict:
    """Get list of referred companies."""
    referrals = (
        db.query(AffiliateReferral)
        .filter(AffiliateReferral.affiliate_id == affiliate.id)
        .order_by(AffiliateReferral.signed_up_at.desc())
        .all()
    )

    referral_list = []
    for ref in referrals:
        company = db.query(Company).filter(Company.id == ref.referred_company_id).first()
        referral_list.append(
            AffiliateReferralResponse(
                id=ref.id,
                referred_company_email=company.email if company else "unknown",
                status=ref.status,
                commission_amount=ref.commission_amount,
                signed_up_at=ref.signed_up_at.isoformat(),
                converted_at=ref.converted_at.isoformat() if ref.converted_at else None,
            )
        )

    return {
        "referrals": referral_list,
        "total": len(referral_list),
    }


# ââ Admin endpoints ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ


@router.get("/admin/list")
def list_affiliates(
    x_admin_key: str = Depends(_get_admin_key),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: list all affiliates with stats."""
    affiliates = db.query(Affiliate).all()
    result = []

    for aff in affiliates:
        referrals = db.query(AffiliateReferral).filter(
            AffiliateReferral.affiliate_id == aff.id
        ).all()
        signups = len(referrals)
        conversions = len([r for r in referrals if r.status == "converted"])

        result.append(
            AdminAffiliateResponse(
                id=aff.id,
                name=aff.name,
                email=aff.email,
                code=aff.code,
                status=aff.status,
                commission_pct=aff.commission_pct,
                total_earned=aff.total_earned,
                total_paid=aff.total_paid,
                signups=signups,
                conversions=conversions,
                created_at=aff.created_at.isoformat(),
            )
        )

    return {"affiliates": result}


@router.patch("/admin/{affiliate_id}")
def update_affiliate(
    affiliate_id: str,
    commission_pct: float | None = None,
    status: str | None = None,
    notes: str | None = None,
    x_admin_key: str = Depends(_get_admin_key),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: approve/reject/update affiliate."""
    affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()
    if not affiliate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Affiliate not found")

    if status and status in ("active", "rejected"):
        affiliate.status = status
        if status == "active":
            affiliate.approved_at = datetime.utcnow()

    if commission_pct is not None and commission_pct > 0:
        affiliate.commission_pct = commission_pct

    if notes is not None:
        affiliate.notes = notes

    db.commit()
    db.refresh(affiliate)

    logger.info("Updated affiliate %s: status=%s, commission_pct=%s", affiliate_id, status, commission_pct)
    return {"message": "Affiliate updated", "affiliate_id": affiliate.id}


@router.post("/admin/{affiliate_id}/payout")
def record_payout(
    affiliate_id: str,
    body: AdminPayoutRequest,
    x_admin_key: str = Depends(_get_admin_key),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: record a payout for an affiliate."""
    affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()
    if not affiliate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Affiliate not found")

    payout = AffiliatePayout(
        affiliate_id=affiliate.id,
        amount=body.amount,
        notes=body.notes,
    )
    db.add(payout)

    # Update affiliate total_paid
    affiliate.total_paid += body.amount

    db.commit()
    db.refresh(payout)

    logger.info("Recorded payout for affiliate %s: $%.2f", affiliate_id, body.amount)
    return {
        "message": "Payout recorded",
        "payout_id": payout.id,
        "amount": body.amount,
    }
