import hashlib
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import HTTPException, status
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

logger = logging.getLogger("auto_interview.auth")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


# ── Password policy ───────────────────────────────────────────────────

def validate_password_strength(password: str) -> None:
    """Enforce the password policy: ≥8 chars with at least one letter and
    one digit. Raises 400 with a user-readable message. Called at signup,
    change-password, and reset-confirm (the three places a password is set).
    """
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters.",
        )
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one letter and one number.",
        )


def is_password_breached(password: str) -> bool:
    """Check the password against haveibeenpwned via the k-anonymity range
    API (only the first 5 chars of the SHA-1 leave the server). Fail-open:
    any network / parsing error returns False so an HIBP outage can never
    block signups. Only runs when enabled (production, or explicitly via
    PASSWORD_BREACH_CHECK).
    """
    if not (settings.PASSWORD_BREACH_CHECK or settings.is_production):
        return False
    digest = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = digest[:5], digest[5:]
    try:
        resp = httpx.get(
            f"https://api.pwnedpasswords.com/range/{prefix}",
            timeout=2.0,
            headers={"Add-Padding": "true"},
        )
        resp.raise_for_status()
        for line in resp.text.splitlines():
            candidate, _, count = line.partition(":")
            if candidate.strip().upper() == suffix and int(count or 0) > 0:
                return True
    except Exception:  # pragma: no cover — fail-open by design
        logger.warning("HIBP breach check unavailable; allowing password")
    return False


def require_acceptable_password(password: str) -> None:
    """Full password gate: strength policy + breach check."""
    validate_password_strength(password)
    if is_password_breached(password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This password appears in known data breaches. "
                "Please choose a different one."
            ),
        )


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWTs ──────────────────────────────────────────────────────────────

def company_token_claims(company) -> dict:
    """Standard claims for a company session token. The "tv" claim pins the
    token to the company's current token_version — bumping the column
    revokes every outstanding token (logout-everywhere, password change,
    suspension)."""
    return {"sub": company.id, "tv": company.token_version or 0}


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_impersonation_token(company_id: str, admin_identity: str) -> str:
    to_encode = {"sub": company_id, "impersonation": True, "admin_identity": admin_identity}
    expire = datetime.now(timezone.utc) + timedelta(hours=1)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_2fa_pending_token(company_id: str) -> str:
    """Short-lived token proving the password step of a 2FA login passed.
    Exchanged (with a valid TOTP / backup code) for real session tokens."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    return jwt.encode(
        {"sub": company_id, "exp": expire, "type": "2fa_pending"},
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_2fa_pending_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "2fa_pending":
            raise JWTError("wrong type")
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired 2FA session. Please sign in again.",
        )


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        # Guard against type-confusion: refresh tokens (30d lifetime) must
        # never be accepted where an access token (24h) is expected.
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def decode_refresh_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired refresh token",
            )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )


def check_token_version(payload: dict, company) -> None:
    """Reject tokens minted before the last revocation event. Impersonation
    tokens are exempt — they're admin-minted, 1h-lived, and don't carry the
    claim."""
    if payload.get("impersonation"):
        return
    if int(payload.get("tv", 0)) != int(company.token_version or 0):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── TOTP two-factor auth ──────────────────────────────────────────────

TOTP_ISSUER = "QualiPulse"
BACKUP_CODE_COUNT = 10


def generate_totp_secret() -> str:
    import pyotp

    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, account_email: str) -> str:
    import pyotp

    return pyotp.TOTP(secret).provisioning_uri(
        name=account_email, issuer_name=TOTP_ISSUER
    )


def verify_totp_code(secret: str, code: str) -> bool:
    import pyotp

    code = (code or "").strip().replace(" ", "")
    if not code:
        return False
    # valid_window=1 tolerates one 30s step of clock drift either way.
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_backup_codes() -> tuple[list[str], str]:
    """Return (plaintext codes shown once, JSON of SHA-256 digests to store)."""
    codes = [
        f"{secrets.token_hex(4)}-{secrets.token_hex(4)}"
        for _ in range(BACKUP_CODE_COUNT)
    ]
    hashed = [hashlib.sha256(c.encode("utf-8")).hexdigest() for c in codes]
    return codes, json.dumps(hashed)


def consume_backup_code(stored_json: str | None, code: str) -> str | None:
    """If ``code`` matches an unused backup code, return the updated JSON
    with that code removed; otherwise None. Single-use by construction."""
    if not stored_json:
        return None
    code = (code or "").strip().lower().replace(" ", "")
    if not code:
        return None
    try:
        hashes: list[str] = json.loads(stored_json)
    except (TypeError, ValueError):
        return None
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    if digest not in hashes:
        return None
    hashes.remove(digest)
    return json.dumps(hashes)
