"""SendGrid Event Webhook + recipient unsubscribe endpoints.

Closes the delivery feedback loop. Before this existed, a hard bounce or a
spam report was invisible to the app: we kept mailing dead addresses, which
is one of the fastest ways to burn a sending domain's reputation.

Routes
------
``POST /email/events``      SendGrid Event Webhook receiver (ECDSA-verified)
``POST /email/unsubscribe`` RFC 8058 one-click target (Gmail/Outlook call this)
``GET  /email/unsubscribe`` human-facing confirmation page

All three are public by necessity — they are called by mailbox providers,
not by our authenticated frontend — so the webhook is authenticated by
signature and the unsubscribe routes by a signed token.
"""
import base64
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.limiter import limiter
from app.models.email_suppression import (
    REASON_BOUNCE,
    REASON_SPAM_REPORT,
    REASON_UNSUBSCRIBE,
)
from app.services.email_suppression import read_unsubscribe_token, suppress

logger = logging.getLogger("auto_interview.email")

router = APIRouter(prefix="/email", tags=["email"])

_SIGNATURE_HEADER = "X-Twilio-Email-Event-Webhook-Signature"
_TIMESTAMP_HEADER = "X-Twilio-Email-Event-Webhook-Timestamp"

# Reject signed payloads older than this to blunt replay attempts.
_MAX_SIGNATURE_AGE_SECONDS = 600


def _verify_sendgrid_signature(
    raw_body: bytes, signature: Optional[str], timestamp: Optional[str]
) -> bool:
    """Verify SendGrid's ECDSA (P-256/SHA-256) event-webhook signature.

    Implemented directly against ``cryptography`` rather than SendGrid's
    ``EventWebhook`` helper, which needs the extra ``starkbank-ecdsa``
    dependency. The signed message is ``timestamp + raw_body``, and the
    configured public key is base64 DER (exactly as SendGrid displays it).
    """
    public_key_b64 = (settings.SENDGRID_WEBHOOK_PUBLIC_KEY or "").strip()
    if not public_key_b64 or not signature or not timestamp:
        return False

    # Replay window. A missing/garbage timestamp fails closed.
    try:
        age = abs(time.time() - int(timestamp))
    except (TypeError, ValueError):
        return False
    if age > _MAX_SIGNATURE_AGE_SECONDS:
        logger.warning("SendGrid webhook signature too old (%ss); rejecting", int(age))
        return False

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import load_der_public_key

        key = load_der_public_key(base64.b64decode(public_key_b64))
        key.verify(
            base64.b64decode(signature),
            timestamp.encode("utf-8") + raw_body,
            ec.ECDSA(hashes.SHA256()),
        )
        return True
    except InvalidSignature:
        logger.warning("SendGrid webhook signature did not verify")
        return False
    except Exception:  # noqa: BLE001 — malformed key/signature, missing lib
        logger.exception("SendGrid webhook signature verification errored")
        return False


def _reason_for_event(event: dict) -> Optional[str]:
    """Map one SendGrid event to a suppression reason, or None to ignore.

    Only terminal states suppress. A ``blocked`` bounce is typically a
    transient receiving-side deferral (greylisting, full mailbox), so
    suppressing on it would permanently cut off recoverable addresses.
    """
    name = (event.get("event") or "").lower()
    if name == "bounce":
        # SendGrid marks hard bounces type="bounce", soft/blocked type="blocked".
        return REASON_BOUNCE if (event.get("type") or "").lower() != "blocked" else None
    if name == "dropped":
        # SendGrid refused to send — already on their internal suppression list.
        return REASON_BOUNCE
    if name == "spamreport":
        return REASON_SPAM_REPORT
    if name in ("unsubscribe", "group_unsubscribe"):
        return REASON_UNSUBSCRIBE
    return None


@router.post("/events")
@limiter.limit(settings.RATE_LIMIT_PUBLIC)
async def sendgrid_events(request: Request, db: Session = Depends(get_db)):
    """Receive a SendGrid event batch and update the suppression list.

    Always returns 2xx on a *verified* payload, even for events we ignore —
    SendGrid retries non-2xx responses and a retry storm helps nobody.
    Unverified payloads get 403 so a stranger cannot poison the suppression
    list and silently cut off our own delivery.
    """
    raw_body = await request.body()
    verified = _verify_sendgrid_signature(
        raw_body,
        request.headers.get(_SIGNATURE_HEADER),
        request.headers.get(_TIMESTAMP_HEADER),
    )

    if not verified:
        # In production an unverifiable payload is always rejected. In dev the
        # key is usually unset, so allow unsigned posts to keep local testing
        # possible — but never when a key IS configured.
        if settings.is_production or settings.SENDGRID_WEBHOOK_PUBLIC_KEY:
            return Response(status_code=403)
        logger.warning(
            "Accepting UNVERIFIED SendGrid webhook (dev only — "
            "set SENDGRID_WEBHOOK_PUBLIC_KEY)"
        )

    try:
        events = json.loads(raw_body or b"[]")
    except ValueError:
        logger.warning("SendGrid webhook sent non-JSON body")
        return {"received": 0, "suppressed": 0}
    if not isinstance(events, list):
        return {"received": 0, "suppressed": 0}

    suppressed = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        email = event.get("email")
        reason = _reason_for_event(event)
        if not email or not reason:
            continue
        row = suppress(
            db,
            email=email,
            reason=reason,
            source="sendgrid_webhook",
            detail=json.dumps(event)[:2000],
        )
        if row is not None:
            suppressed += 1
            logger.info(
                "Suppressing %s (reason=%s, sg_event=%s)",
                email,
                reason,
                event.get("event"),
            )
    db.commit()
    return {"received": len(events), "suppressed": suppressed}


# ── Unsubscribe ────────────────────────────────────────────────────────────


def _withdraw_panel_consent(db: Session, email: str) -> None:
    """Mirror an unsubscribe onto recontact consent.

    Suppressing delivery alone would leave the person in the workspace
    recruit pool: researchers would keep "inviting" them and see invites
    that silently never send. Withdrawing consent removes them from the
    pool itself, matching what ``POST /panel/opt-out`` does.
    """
    from sqlalchemy import func

    from app.models.interview import Participant
    from app.models.panel import PanelProfile

    profile = (
        db.query(PanelProfile)
        .filter(func.lower(PanelProfile.email) == email.lower())
        .first()
    )
    if profile is not None and profile.panel_consent:
        profile.panel_consent = False
    for participant in (
        db.query(Participant).filter(func.lower(Participant.email) == email.lower()).all()
    ):
        participant.panel_consent = False


def _unsubscribe(db: Session, token: str) -> bool:
    address = read_unsubscribe_token(token)
    if not address:
        return False
    suppress(
        db,
        email=address,
        reason=REASON_UNSUBSCRIBE,
        source="recipient",
        detail="one-click unsubscribe",
    )
    try:
        _withdraw_panel_consent(db, address)
    except Exception:  # noqa: BLE001 — the suppression is what must land.
        logger.exception("Could not withdraw panel consent for %s", address)
    db.commit()
    logger.info("Unsubscribed %s via one-click", address)
    return True


@router.post("/unsubscribe")
@limiter.limit(settings.RATE_LIMIT_PUBLIC)
async def unsubscribe_one_click(
    request: Request, token: str = "", db: Session = Depends(get_db)
) -> PlainTextResponse:
    """RFC 8058 one-click target, called by the mailbox provider, not a human.

    Gmail POSTs ``List-Unsubscribe=One-Click`` here with no user interaction,
    so there is nothing to confirm and nothing to render. Returning anything
    other than 2xx makes Gmail treat our unsubscribe as broken.
    """
    ok = _unsubscribe(db, token)
    if not ok:
        return PlainTextResponse("Invalid unsubscribe token", status_code=400)
    return PlainTextResponse("Unsubscribed", status_code=200)


@router.get("/unsubscribe", response_class=HTMLResponse)
@limiter.limit(settings.RATE_LIMIT_PUBLIC)
async def unsubscribe_page(
    request: Request, token: str = "", db: Session = Depends(get_db)
) -> HTMLResponse:
    """Human-facing fallback for clients that render the mailto/link instead.

    Kept to plain markup with inline styles only: API responses carry a
    ``default-src 'none'`` CSP that allows inline styles but no scripts.
    """
    ok = _unsubscribe(db, token)
    heading = "You're unsubscribed" if ok else "Link not recognised"
    body = (
        "You won't receive further research invitations from QualiPulse. "
        "Account and security emails are unaffected."
        if ok
        else "This unsubscribe link is invalid or has already been replaced. "
        "Reply to any QualiPulse email and we'll remove you by hand."
    )
    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{heading} - QualiPulse</title></head>
<body style="margin:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:480px;margin:0 auto;padding:64px 24px;text-align:center;">
    <p style="font-size:1.2rem;font-weight:700;color:#4f46e5;margin:0 0 32px;">QualiPulse</p>
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:32px;">
      <h1 style="margin:0 0 12px;font-size:1.25rem;color:#0f172a;">{heading}</h1>
      <p style="color:#475569;line-height:1.6;margin:0;">{body}</p>
    </div>
  </div>
</body></html>"""
    return HTMLResponse(content=html, status_code=200 if ok else 400)
