import hmac
import json
import logging
import re
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.limiter import limiter
from app.models.admin_audit import AdminAuditLog
from app.models.company import Company
from app.models.affiliate import Affiliate, AffiliateReferral, AffiliatePayout
from app.services.auth import create_access_token

logger = logging.getLogger("auto_interview.affiliate")
router = APIRouter(prefix="/affiliates", tags=["affiliates"])


# ââ Schemas ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ


class AffiliateApplyRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    code: str
    website: str | None = None
    how_they_found_us: str | None = Field(default=None, max_length=1000)

    @field_validator("website")
    @classmethod
    def validate_website(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("Website must start with http:// or https://")
        return v


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


class AffiliatePayoutResponse(BaseModel):
    id: str
    amount: float
    paid_at: str
    notes: str | None


class AdminAffiliateResponse(BaseModel):
    id: str
    name: str
    email: str
    code: str
    status: str
    commission_pct: float
    total_earned: float
    total_paid: float
    pending_earnings: float
    payout_threshold: float
    signups: int
    conversions: int
    website: str | None
    how_they_found_us: str | None
    notes: str | None
    created_at: str
    approved_at: str | None


class AdminAffiliateUpdate(BaseModel):
    commission_pct: float | None = Field(default=None, gt=0, le=100)
    status: str | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AdminPayoutRequest(BaseModel):
    amount: float = Field(gt=0)
    notes: str | None = Field(default=None, max_length=2000)


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


def _get_admin_identity(
    authorization: str | None = Header(default=None),
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
    x_admin_identity: str | None = Header(default=None, alias="X-Admin-Identity"),
) -> str:
    """Verify the admin key (timing-safe) and return the admin identity for audit logging.

    Accepts both `Authorization: Bearer <key>` (what the admin panel sends,
    same as routers/admin.py) and the legacy `X-Admin-Key` header.
    """
    if not settings.ADMIN_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access is disabled",
        )
    token = x_admin_key
    if token is None and authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):]
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing admin key",
        )
    if not hmac.compare_digest(token, settings.ADMIN_SECRET_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin key",
        )
    return (x_admin_identity or "unknown").strip()[:100]


def _record_affiliate_audit(
    db: Session,
    admin_identity: str,
    action: str,
    affiliate: Affiliate,
    details: dict | None = None,
) -> None:
    db.add(AdminAuditLog(
        id=str(uuid.uuid4()),
        admin_identity=admin_identity,
        action=action,
        target_company_id=affiliate.company_id,
        target_company_email=affiliate.email,
        details=json.dumps(details) if details else None,
    ))


def _referral_counts(db: Session, affiliate_ids: list[str]) -> dict[str, tuple[int, int]]:
    """Signup + conversion counts per affiliate in one grouped query.

    Conversions include referrals whose commission has already been paid out
    (status flows signed_up → converted → paid)."""
    if not affiliate_ids:
        return {}
    rows = (
        db.query(
            AffiliateReferral.affiliate_id,
            func.count(AffiliateReferral.id),
            func.sum(
                case((AffiliateReferral.status.in_(("converted", "paid")), 1), else_=0)
            ),
        )
        .filter(AffiliateReferral.affiliate_id.in_(affiliate_ids))
        .group_by(AffiliateReferral.affiliate_id)
        .all()
    )
    return {aff_id: (int(total), int(converted or 0)) for aff_id, total, converted in rows}


def _get_affiliate_from_jwt(
    credentials: str,
    db: Session,
) -> Affiliate:
    """Extract affiliate_id from JWT and fetch affiliate."""
    from app.services.auth import decode_access_token

    payload = decode_access_token(credentials)
    sub: str | None = payload.get("sub")
    # Affiliate ids are uuid4 strings — reject anything that isn't exactly
    # "affiliate:<uuid>" so a crafted sub can't smuggle a different id shape.
    if not sub or not re.fullmatch(r"affiliate:[0-9a-f-]{36}", sub):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid affiliate token",
        )
    affiliate_id = sub[len("affiliate:"):]
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
            detail="An application with this email already exists.",
        )

    # Validate and normalize code
    code = _validate_affiliate_code(body.code)

    # Check if code is already taken
    existing_code = db.query(Affiliate).filter(Affiliate.code == code).first()
    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This affiliate code is already taken. Try a different name.",
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
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> Affiliate:
    """Dependency: extract affiliate from the Authorization: Bearer JWT."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )
    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    return _get_affiliate_from_jwt(token, db)


@router.get("/me", response_model=AffiliateStatsResponse)
def get_affiliate_stats(
    affiliate: Affiliate = Depends(get_current_affiliate),
    db: Session = Depends(get_db),
) -> AffiliateStatsResponse:
    """Get affiliate stats and earnings."""
    signups, conversions = _referral_counts(db, [affiliate.id]).get(affiliate.id, (0, 0))
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
        referral_link=f"{settings.APP_BASE_URL}/?ref={affiliate.code}",
    )


@router.get("/me/link")
def get_affiliate_link(affiliate: Affiliate = Depends(get_current_affiliate)) -> dict:
    """Get shareable referral link."""
    return {
        "referral_link": f"{settings.APP_BASE_URL}/?ref={affiliate.code}",
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


@router.get("/me/payouts")
def get_affiliate_payouts(
    affiliate: Affiliate = Depends(get_current_affiliate),
    db: Session = Depends(get_db),
) -> dict:
    """Get payout history for the current affiliate."""
    payouts = (
        db.query(AffiliatePayout)
        .filter(AffiliatePayout.affiliate_id == affiliate.id)
        .order_by(AffiliatePayout.paid_at.desc())
        .all()
    )
    return {
        "payouts": [
            AffiliatePayoutResponse(
                id=p.id,
                amount=p.amount,
                paid_at=p.paid_at.isoformat(),
                notes=p.notes,
            )
            for p in payouts
        ],
        "total": len(payouts),
    }


# ââ Admin endpoints ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ


def _admin_affiliate_response(aff: Affiliate, signups: int, conversions: int) -> AdminAffiliateResponse:
    return AdminAffiliateResponse(
        id=aff.id,
        name=aff.name,
        email=aff.email,
        code=aff.code,
        status=aff.status,
        commission_pct=aff.commission_pct,
        total_earned=aff.total_earned,
        total_paid=aff.total_paid,
        pending_earnings=aff.total_earned - aff.total_paid,
        payout_threshold=aff.payout_threshold,
        signups=signups,
        conversions=conversions,
        website=aff.website,
        how_they_found_us=aff.how_they_found_us,
        notes=aff.notes,
        created_at=aff.created_at.isoformat(),
        approved_at=aff.approved_at.isoformat() if aff.approved_at else None,
    )


@router.get("/admin/list")
def list_affiliates(
    admin_identity: str = Depends(_get_admin_identity),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: list all affiliates with stats."""
    affiliates = db.query(Affiliate).order_by(Affiliate.created_at.desc()).all()
    counts = _referral_counts(db, [a.id for a in affiliates])
    return {
        "affiliates": [
            _admin_affiliate_response(aff, *counts.get(aff.id, (0, 0)))
            for aff in affiliates
        ]
    }


@router.patch("/admin/{affiliate_id}")
def update_affiliate(
    affiliate_id: str,
    body: AdminAffiliateUpdate,
    admin_identity: str = Depends(_get_admin_identity),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: approve/reject/update affiliate."""
    affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()
    if not affiliate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Affiliate not found",
        )

    if body.status is not None:
        if affiliate.status != "pending" or body.status not in ("active", "rejected"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot change status from {affiliate.status} to {body.status}. Only pending affiliates can be approved or rejected.",
            )
        old_status = affiliate.status
        affiliate.status = body.status
        if body.status == "active":
            affiliate.approved_at = datetime.utcnow()
        _record_affiliate_audit(
            db, admin_identity, "affiliate_status_change", affiliate,
            {"from": old_status, "to": body.status},
        )

    if body.commission_pct is not None and body.commission_pct != affiliate.commission_pct:
        _record_affiliate_audit(
            db, admin_identity, "affiliate_commission_change", affiliate,
            {"from": affiliate.commission_pct, "to": body.commission_pct},
        )
        affiliate.commission_pct = body.commission_pct

    if body.notes is not None:
        affiliate.notes = body.notes

    db.commit()
    db.refresh(affiliate)

    logger.info("Updated affiliate %s: status=%s, commission_pct=%s", affiliate_id, body.status, body.commission_pct)
    signups, conversions = _referral_counts(db, [affiliate.id]).get(affiliate.id, (0, 0))
    return {
        "message": "Affiliate updated",
        "affiliate_id": affiliate.id,
        "affiliate": _admin_affiliate_response(affiliate, signups, conversions),
    }


@router.post("/admin/{affiliate_id}/payout")
def record_payout(
    affiliate_id: str,
    body: AdminPayoutRequest,
    admin_identity: str = Depends(_get_admin_identity),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: record a payout for an affiliate."""
    affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()
    if not affiliate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Affiliate not found")

    pending = affiliate.total_earned - affiliate.total_paid
    if body.amount > pending + 1e-9:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payout of ${body.amount:.2f} exceeds pending earnings of ${pending:.2f}.",
        )

    payout = AffiliatePayout(
        affiliate_id=affiliate.id,
        amount=body.amount,
        notes=body.notes,
    )
    db.add(payout)
    affiliate.total_paid += body.amount
    _record_affiliate_audit(
        db, admin_identity, "affiliate_payout", affiliate,
        {"amount": body.amount, "notes": body.notes},
    )

    db.commit()
    db.refresh(payout)

    logger.info("Recorded payout for affiliate %s: $%.2f", affiliate_id, body.amount)
    return {
        "message": "Payout recorded",
        "payout_id": payout.id,
        "amount": body.amount,
        "total_paid": affiliate.total_paid,
        "pending_earnings": affiliate.total_earned - affiliate.total_paid,
    }


@router.get("/admin/{affiliate_id}/payouts")
def list_affiliate_payouts(
    affiliate_id: str,
    admin_identity: str = Depends(_get_admin_identity),
    db: Session = Depends(get_db),
) -> dict:
    """Admin: payout history for one affiliate."""
    affiliate = db.query(Affiliate).filter(Affiliate.id == affiliate_id).first()
    if not affiliate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Affiliate not found")

    payouts = (
        db.query(AffiliatePayout)
        .filter(AffiliatePayout.affiliate_id == affiliate.id)
        .order_by(AffiliatePayout.paid_at.desc())
        .all()
    )
    return {
        "payouts": [
            AffiliatePayoutResponse(
                id=p.id,
                amount=p.amount,
                paid_at=p.paid_at.isoformat(),
                notes=p.notes,
            )
            for p in payouts
        ],
        "total": len(payouts),
    }
