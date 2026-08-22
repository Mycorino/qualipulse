"""
Participant email verification via magic links.
"""
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import ParticipantMagicToken


# Recontact invites are read hours or days after they land, so their token
# cannot expire on the 30-minute verification clock. Two weeks comfortably
# covers a weekend plus a reminder without leaving links valid indefinitely.
INVITE_TOKEN_EXPIRY_MINUTES = 14 * 24 * 60

# Wrong code entries allowed per token before it is dead. Six digits is a
# million combinations, which is only safe behind a hard cap: without one,
# the endpoint's per-IP rate limit alone would let a determined caller walk
# the space from a handful of addresses.
MAX_CODE_ATTEMPTS = 5


def generate_numeric_code(digits: int = 6) -> str:
    """A cryptographically random numeric code, leading zeros preserved."""
    return "".join(secrets.choice("0123456789") for _ in range(digits))


def mint_magic_credentials(
    db: Session,
    email: str,
    interview_link_token: str,
    expiry_minutes: int = 30,
    reusable: bool = False,
) -> tuple[str, str]:
    """Create and persist a magic token, returning ``(token, code)``.

    Both routes come from one send: the link for a one-tap open when that
    works, the six-digit code for when it does not. See ``mint_magic_token``
    for the token-only wrapper kept for existing callers.

    Used directly by the interview-reminder emails, which embed the magic
    URL in their own template instead of the standard verification email,
    and by recontact invites (see ``reusable``).

    ``reusable`` tokens are not burned by ``verify_magic_token``. Invite
    links need this: the session JWT a click issues lasts only 2 hours, so a
    single-use invite would lock a panelist out of their own invitation as
    soon as they stepped away, with no self-serve way to request another.
    It stays safe because the token is bound to one email and the
    one-completed-interview-per-email-per-link guard is unchanged.

    Every token also carries a six-digit ``code`` for the OTP path (see
    ``verify_code``), so the caller can offer both routes from one send.
    """
    # Use base58-safe alphabet (no ambiguous chars)
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
    token = "".join(secrets.choice(alphabet) for _ in range(48))

    expires_at = datetime.utcnow() + timedelta(minutes=expiry_minutes)

    db_token = ParticipantMagicToken(
        email=email,
        token=token,
        interview_link_token=interview_link_token,
        expires_at=expires_at,
        reusable=reusable,
        code=generate_numeric_code(),
    )
    db.add(db_token)
    db.commit()
    return token, db_token.code


def mint_magic_token(
    db: Session,
    email: str,
    interview_link_token: str,
    expiry_minutes: int = 30,
    reusable: bool = False,
) -> str:
    """``mint_magic_credentials`` for callers that only need the link."""
    token, _code = mint_magic_credentials(
        db, email, interview_link_token, expiry_minutes, reusable
    )
    return token


def magic_link_url(token: str, lang: str = "en") -> str:
    """The frontend verify URL for a magic token.

    Carries the participant's chosen language in the link so the verify page
    can lock the UI before any pre-interview screen renders — critical when
    the link is opened in a fresh webview (e.g. the email app's in-app
    browser) where localStorage from the original tab isn't available.
    """
    safe_lang = (lang or "en").lower()[:2]
    return f"{settings.APP_BASE_URL}/interview/verify/{token}?lang={safe_lang}"


def generate_magic_token(
    db: Session,
    email: str,
    interview_link_token: str,
    expiry_minutes: int = 30,
    lang: str = "en",
) -> tuple[str, bool]:
    """Generate a magic link token, store it, and send the verification email.

    Returns
    -------
    (token, delivered)
        ``token`` is the freshly-minted magic token (already stored in the
        DB). ``delivered`` is ``True`` if SendGrid accepted the email,
        ``False`` if the send failed. The token is always persisted so the
        caller can retry or surface it to the user.
    """
    token, code = mint_magic_credentials(db, email, interview_link_token, expiry_minutes)

    from app.services.email import send_interview_magic_link
    delivered = send_interview_magic_link(
        email=email,
        magic_url=magic_link_url(token, lang),
        expiry_minutes=expiry_minutes,
        lang=lang,
        code=code,
    )

    return token, delivered


def verify_magic_token(db: Session, token: str) -> ParticipantMagicToken | None:
    """Validate a magic token. Marks it used and returns the record if valid."""
    record = (
        db.query(ParticipantMagicToken)
        .filter(
            ParticipantMagicToken.token == token,
            ParticipantMagicToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if record is None:
        return None
    # Reusable (invite) tokens stay valid until they expire; everything else
    # is single-use and burns on first successful verification.
    if record.reusable:
        return record
    if record.used:
        return None
    record.used = True
    db.commit()
    return record


class CodeResult:
    """Outcome of a code check, so the caller can pick the right HTTP status
    and the participant gets an actionable message rather than a generic
    failure."""

    OK = "ok"
    INVALID = "invalid"          # wrong code, attempts remain
    EXPIRED = "expired"          # no live token for this email/link
    TOO_MANY_ATTEMPTS = "too_many_attempts"


def verify_code(
    db: Session, email: str, interview_link_token: str, code: str
) -> tuple[str, ParticipantMagicToken | None]:
    """Check a six-digit code for an (email, link) pair.

    Returns ``(CodeResult.*, record_or_None)``. Only the newest live token
    for that pair is considered, so a resend immediately invalidates the
    previous code rather than leaving several valid at once.

    A wrong code increments ``code_attempts`` and the token dies at
    ``MAX_CODE_ATTEMPTS``: six digits is a million combinations, which the
    endpoint's per-IP rate limit alone would not protect.
    """
    normalised = "".join(ch for ch in (code or "") if ch.isdigit())
    email_norm = (email or "").strip().lower()
    if not normalised or not email_norm:
        return CodeResult.INVALID, None

    record = (
        db.query(ParticipantMagicToken)
        .filter(
            ParticipantMagicToken.email == email_norm,
            ParticipantMagicToken.interview_link_token == interview_link_token,
            ParticipantMagicToken.code.isnot(None),
            ParticipantMagicToken.expires_at > datetime.utcnow(),
        )
        .order_by(ParticipantMagicToken.created_at.desc())
        .first()
    )
    if record is None:
        return CodeResult.EXPIRED, None
    if (record.code_attempts or 0) >= MAX_CODE_ATTEMPTS:
        return CodeResult.TOO_MANY_ATTEMPTS, None
    # Single-use tokens already spent by the link route must not be replayable.
    if record.used and not record.reusable:
        return CodeResult.EXPIRED, None

    # compare_digest so a wrong code cannot be narrowed by response timing.
    if not hmac.compare_digest(str(record.code), normalised):
        record.code_attempts = (record.code_attempts or 0) + 1
        db.commit()
        if record.code_attempts >= MAX_CODE_ATTEMPTS:
            return CodeResult.TOO_MANY_ATTEMPTS, None
        return CodeResult.INVALID, None

    if not record.reusable:
        record.used = True
    db.commit()
    return CodeResult.OK, record
