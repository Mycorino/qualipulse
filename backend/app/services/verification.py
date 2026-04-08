"""
Participant email verification via magic links.
"""
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import ParticipantMagicToken


def generate_magic_token(
    db: Session,
    email: str,
    interview_link_token: str,
    expiry_minutes: int = 30,
) -> str:
    """Generate a magic link token, store it, and send the verification email."""
    # Use base58-safe alphabet (no ambiguous chars)
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    token = "".join(secrets.choice(alphabet) for _ in range(48))

    expires_at = datetime.utcnow() + timedelta(minutes=expiry_minutes)

    db_token = ParticipantMagicToken(
        email=email,
        token=token,
        interview_link_token=interview_link_token,
        expires_at=expires_at,
    )
    db.add(db_token)
    db.commit()

    magic_url = f"{settings.APP_BASE_URL}/interview/verify/{token}"

    from app.services.email import send_interview_magic_link
    send_interview_magic_link(email=email, magic_url=magic_url, expiry_minutes=expiry_minutes)

    return token


def verify_magic_token(db: Session, token: str) -> ParticipantMagicToken | None:
    """Validate a magic token. Marks it used and returns the record if valid."""
    record = (
        db.query(ParticipantMagicToken)
        .filter(
            ParticipantMagicToken.token == token,
            ParticipantMagicToken.used.is_(False),
            ParticipantMagicToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if record:
        record.used = True
        db.commit()
    return record
