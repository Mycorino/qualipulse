"""Admin authentication: named accounts with mandatory TOTP.

Three guards, from strongest to weakest:

``require_admin``
    The human-facing guard for every ``/admin/*`` and ``/affiliates/admin/*``
    endpoint. Accepts an **admin token**: a 30-minute JWT minted by
    ``POST /admin/session`` after a staff account (``Company.is_admin``)
    presents a fresh TOTP code. The token carries the account's
    ``token_version`` so a password change / logout-everywhere revokes it,
    and it is re-checked against the row on every call so revoking
    ``is_admin`` or suspending the account takes effect immediately.

    During rollout it also accepts the shared ``ADMIN_SECRET_KEY`` when
    ``ADMIN_ALLOW_SHARED_KEY`` is on. Flip that off once every admin has an
    account; the shared key then only opens the service endpoints below.

``require_step_up``
    Layered on top of ``require_admin`` for destructive actions (delete,
    impersonate, credits, purge). Demands a *fresh* TOTP code in the
    ``X-Admin-Step-Up`` header, verified on the spot. A stolen admin token
    alone cannot delete a customer.

``require_service_key``
    Machine credential for the cron endpoints (lifecycle emails, retention
    purge). Always the shared key, never an admin token: a human token must
    not be able to trigger a purge from a browser tab without step-up, and
    Cloud Scheduler cannot do TOTP.

Identity is never self-declared: the audit log gets the verified email from
the token (or ``shared-key:<typed name>`` for the legacy path, so the two
are distinguishable forever in the log).
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.models.company import Company
from app.services.auth import ALGORITHM, consume_backup_code, verify_totp_code

ADMIN_TOKEN_MINUTES = 30
STEP_UP_HEADER = "X-Admin-Step-Up"


@dataclass
class AdminPrincipal:
    identity: str
    company: Optional[Company]  # None on the shared-key path
    via: str  # "account" | "shared_key"


# ── Tokens ──────────────────────────────────────────────────────────────────

def create_admin_token(company: Company) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ADMIN_TOKEN_MINUTES)
    return jwt.encode(
        {
            "sub": company.id,
            "tv": company.token_version or 0,
            "exp": expire,
            "type": "admin",
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_admin_token(token: str) -> dict | None:
    """Return the payload for a well-formed, unexpired admin token, else None.
    (None rather than raising so the caller can fall through to the
    shared-key path without leaking which scheme failed.)"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != "admin":
        return None
    return payload


# ── TOTP helpers shared by /admin/session and step-up ───────────────────────

def check_admin_eligible(company: Company) -> None:
    """403 unless this account may hold an admin session right now."""
    if getattr(company, "_is_impersonation", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an admin")
    if not company.is_admin or company.suspended_at is not None:
        # Same message as a plain non-admin: do not confirm the account exists as staff.
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not an admin")
    if not company.totp_enabled or not company.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin_2fa_required",
        )


def verify_admin_code(db: Session, company: Company, code: str, *, allow_backup: bool) -> bool:
    """Verify a TOTP code (optionally a single-use backup code) against the
    account, applying the login lockout counter so codes cannot be brute
    forced. Commits on both paths."""
    now = datetime.utcnow()
    if company.locked_until and company.locked_until > now:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked. Try again later.",
        )
    ok = verify_totp_code(company.totp_secret or "", code)
    if not ok and allow_backup:
        remaining = consume_backup_code(company.totp_backup_codes, code)
        if remaining is not None:
            company.totp_backup_codes = remaining
            ok = True
    if ok:
        company.failed_login_attempts = 0
        company.locked_until = None
    else:
        company.failed_login_attempts = (company.failed_login_attempts or 0) + 1
        if company.failed_login_attempts >= 5:
            company.locked_until = now + timedelta(minutes=15)
    db.commit()
    return ok


# ── Guards ──────────────────────────────────────────────────────────────────

def _bearer(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer "):].strip() or None
    return None


def _shared_key_matches(token: Optional[str]) -> bool:
    return bool(token and settings.ADMIN_SECRET_KEY and hmac.compare_digest(token, settings.ADMIN_SECRET_KEY))


def resolve_admin(
    authorization: Optional[str] = Header(default=None),
    x_admin_identity: Optional[str] = Header(default=None, alias="X-Admin-Identity"),
    db: Session = Depends(get_db),
) -> AdminPrincipal:
    token = _bearer(authorization)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin session required")

    payload = decode_admin_token(token)
    if payload is not None:
        company = db.query(Company).filter(Company.id == payload.get("sub")).first()
        if company is None or int(payload.get("tv", 0)) != int(company.token_version or 0):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin session revoked")
        try:
            check_admin_eligible(company)
        except HTTPException:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access revoked")
        return AdminPrincipal(identity=company.email, company=company, via="account")

    if settings.ADMIN_ALLOW_SHARED_KEY and _shared_key_matches(token):
        who = (x_admin_identity or "unknown").strip()[:80]
        return AdminPrincipal(identity=f"shared-key:{who}", company=None, via="shared_key")

    if not settings.ADMIN_SECRET_KEY and not settings.ADMIN_ALLOW_SHARED_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access is disabled")
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired admin session")


def require_admin(principal: AdminPrincipal = Depends(resolve_admin)) -> str:
    """Audit identity of the calling admin (verified email, or
    ``shared-key:<name>`` on the legacy path)."""
    return principal.identity


def require_step_up(
    principal: AdminPrincipal = Depends(resolve_admin),
    x_admin_step_up: Optional[str] = Header(default=None, alias=STEP_UP_HEADER),
    db: Session = Depends(get_db),
) -> str:
    """``require_admin`` plus a fresh TOTP code for destructive actions."""
    if principal.via == "shared_key":
        # Legacy path has no second factor to step up with. Goes away with
        # ADMIN_ALLOW_SHARED_KEY.
        return principal.identity
    assert principal.company is not None
    if not x_admin_step_up:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_step_up_required")
    if not verify_admin_code(db, principal.company, x_admin_step_up, allow_backup=False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin_step_up_invalid")
    return principal.identity


def require_service_key(authorization: Optional[str] = Header(default=None)) -> str:
    """Cron / machine guard: the shared key only, regardless of rollout flag."""
    if not settings.ADMIN_SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Service access is disabled")
    if not _shared_key_matches(_bearer(authorization)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid service key")
    return "service:scheduler"
