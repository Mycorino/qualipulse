"""Suppression checks + unsubscribe tokens.

Two jobs:

1. Decide whether a given address may receive a given class of mail.
2. Mint and verify the signed tokens that make one-click unsubscribe
   (RFC 8058) work without exposing a raw email address in the URL.

Design note on fail-open
------------------------
:func:`is_suppressed` swallows every database error and returns ``False``.
A delivery guard that fails closed would turn a transient DB blip into
"nobody can reset their password", which is far worse than sending one
extra email to a bounced address.
"""
import logging
from typing import Optional

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models.email_suppression import (
    ALL_REASONS,
    REASON_BOUNCE,
    REASON_MANUAL,
    REASON_SPAM_REPORT,
    REASON_UNSUBSCRIBE,
    EmailSuppression,
)

logger = logging.getLogger("auto_interview.email")

_TOKEN_ALGORITHM = "HS256"
_TOKEN_PURPOSE = "unsubscribe"

# Which reasons block which class of mail.
#
# ``bounce`` and ``manual`` block everything — a nonexistent mailbox can't
# receive a password reset either, and a hand-added suppression is usually a
# support escalation we must honour completely.
#
# ``unsubscribe`` and ``spam_report`` block bulk mail only. A recipient who
# opts out of study invites has not forfeited the ability to reset their own
# password, and silently dropping account-security mail would be a worse
# failure than the complaint it's trying to avoid.
_BLOCKS_ALL_MAIL = frozenset({REASON_BOUNCE, REASON_MANUAL})
_BLOCKS_MARKETING_ONLY = frozenset({REASON_UNSUBSCRIBE, REASON_SPAM_REPORT})


def normalize_email(email: str) -> str:
    """Lowercase + strip. Matches how addresses are stored in the table."""
    return (email or "").strip().lower()


def is_suppressed(db: Session, email: str, email_type: str = "transactional") -> bool:
    """True when ``email`` must not receive mail of class ``email_type``.

    ``email_type`` is the same vocabulary ``send_email`` uses:
    ``"transactional"`` or ``"marketing"``.
    """
    address = normalize_email(email)
    if not address:
        return False

    try:
        row = (
            db.query(EmailSuppression)
            .filter(EmailSuppression.email == address)
            .first()
        )
    except Exception:  # noqa: BLE001 — see module docstring: fail open.
        logger.exception("Suppression lookup failed for %s; allowing send", address)
        return False

    if row is None:
        return False
    if row.reason in _BLOCKS_ALL_MAIL:
        return True
    return email_type == "marketing" and row.reason in _BLOCKS_MARKETING_ONLY


def suppress(
    db: Session,
    email: str,
    reason: str,
    source: str = "sendgrid_webhook",
    detail: Optional[str] = None,
) -> Optional[EmailSuppression]:
    """Add an address to the suppression list. Idempotent.

    The first suppression wins — a later unsubscribe must not downgrade an
    earlier hard bounce, since the reasons carry different blocking power.
    Returns the existing row unchanged in that case, or ``None`` if the
    address or reason was unusable.
    """
    address = normalize_email(email)
    if not address or reason not in ALL_REASONS:
        return None

    existing = (
        db.query(EmailSuppression).filter(EmailSuppression.email == address).first()
    )
    if existing is not None:
        return existing

    row = EmailSuppression(
        email=address,
        reason=reason,
        source=source,
        detail=(detail or "")[:2000] or None,
    )
    db.add(row)
    db.flush()
    return row


# ── Unsubscribe tokens ─────────────────────────────────────────────────────


def make_unsubscribe_token(email: str) -> str:
    """Sign an unsubscribe token for ``email``.

    Deliberately has **no expiry**: an unsubscribe link must still work when
    someone digs up a year-old email, and a dead link there means a spam
    complaint instead of a clean opt-out.
    """
    return jwt.encode(
        {"sub": normalize_email(email), "purpose": _TOKEN_PURPOSE},
        settings.SECRET_KEY,
        algorithm=_TOKEN_ALGORITHM,
    )


def read_unsubscribe_token(token: str) -> Optional[str]:
    """Return the address inside a valid token, else ``None``."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[_TOKEN_ALGORITHM]
        )
    except JWTError:
        return None
    if payload.get("purpose") != _TOKEN_PURPOSE:
        return None
    address = normalize_email(payload.get("sub") or "")
    return address or None
