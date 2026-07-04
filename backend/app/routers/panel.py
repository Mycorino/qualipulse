"""Panel enrichment endpoints — consented panelists progressively add
profiling attributes (post-interview or via the durable emailed link) so we
can re-target them with future studies.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.limiter import limiter
from app.models.panel import PanelAttribute, PanelProfile
from app.services import panel_service as ps

logger = logging.getLogger("auto_interview")

router = APIRouter(prefix="/panel", tags=["panel"])


class AnswerItem(BaseModel):
    attribute_id: str
    value: object  # str | list[str] | bool


class SaveAnswersRequest(BaseModel):
    token: str
    answers: list[AnswerItem]


class TokenRequest(BaseModel):
    token: str


class RequestAccessRequest(BaseModel):
    email: str
    lang: str | None = None


class JoinRequest(BaseModel):
    email: EmailStr
    first_name: str | None = None
    lang: str | None = None
    consent: bool = False


def _profile_or_401(db: Session, token: str | None) -> PanelProfile:
    email = ps.resolve_panel_email(token)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired panel session.",
        )
    profile = db.query(PanelProfile).filter(PanelProfile.email == email).first()
    if profile is None:
        # A consented session should always have a profile, but be defensive.
        profile = PanelProfile(email=email, panel_consent=True, consent_at=datetime.utcnow())
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _visible_attributes(db: Session, lang: str, include_sensitive: bool) -> list[dict]:
    q = db.query(PanelAttribute).filter(PanelAttribute.active.is_(True))
    if not include_sensitive:
        q = q.filter(PanelAttribute.is_sensitive.is_(False))
    rows = q.order_by(PanelAttribute.priority.desc(), PanelAttribute.sort_order.asc()).all()
    return [ps.localize_attribute(a, lang) for a in rows]


@router.get("/attributes")
def get_attributes(lang: str = "en", db: Session = Depends(get_db)):
    """Public, non-sensitive catalogue preview (no PII, no token)."""
    return {"attributes": _visible_attributes(db, lang, include_sensitive=False)}


@router.get("/me")
def get_my_panel(token: str, lang: str = "en", db: Session = Depends(get_db)):
    """The panelist's current answers + completeness + the catalogue they can
    see (sensitive attributes included only after explicit consent)."""
    profile = _profile_or_401(db, token)
    return {
        "email": profile.email,
        "first_name": profile.first_name,
        "sensitive_consent": bool(profile.sensitive_data_consent),
        "completeness": ps.completeness(db, profile),
        "answers": ps.current_answers(profile),
        "attributes": _visible_attributes(db, lang, include_sensitive=bool(profile.sensitive_data_consent)),
    }


@router.post("/answers")
@limiter.limit("60/minute")
def save_answers(request: Request, body: SaveAnswersRequest, db: Session = Depends(get_db)):
    profile = _profile_or_401(db, body.token)
    saved, rejected = ps.upsert_answers(
        db, profile, [{"attribute_id": a.attribute_id, "value": a.value} for a in body.answers]
    )
    return {"saved": saved, "rejected": rejected, "completeness": ps.completeness(db, profile)}


@router.post("/sensitive-consent")
@limiter.limit("20/minute")
def grant_sensitive_consent(request: Request, body: TokenRequest, lang: str = "en", db: Session = Depends(get_db)):
    """Record explicit GDPR special-category consent and reveal sensitive
    attributes."""
    profile = _profile_or_401(db, body.token)
    profile.sensitive_data_consent = True
    profile.sensitive_data_consent_at = datetime.utcnow()
    db.commit()
    return {
        "sensitive_consent": True,
        "attributes": _visible_attributes(db, lang, include_sensitive=True),
    }


@router.post("/join")
@limiter.limit("5/minute")
def join_panel(request: Request, body: JoinRequest, db: Session = Depends(get_db)):
    """Public panel signup (double opt-in). No profile is created here — we
    email a signed confirmation link and only record consent when it comes
    back via /join/confirm. Always 200 (no account enumeration). An
    already-consented panelist gets their regular access link instead."""
    if not body.consent:
        raise HTTPException(status_code=400, detail="Consent is required to join the panel.")
    email = body.email.strip().lower()
    lang = (body.lang or "en")[:2]
    first_name = (body.first_name or "").strip()[:80] or None

    from app.services.email import send_panel_access_link, send_panel_join_confirm

    existing = (
        db.query(PanelProfile)
        .filter(func.lower(PanelProfile.email) == email)
        .first()
    )
    try:
        if existing is not None and existing.panel_consent:
            send_panel_access_link(
                email=existing.email,
                token=ps.create_panel_session(existing.email),
                lang=(body.lang or existing.preferred_language or "en")[:2],
            )
        else:
            send_panel_join_confirm(
                email=email,
                token=ps.create_join_token(email, first_name, lang),
                lang=lang,
            )
    except Exception:  # pragma: no cover — never leak send failures
        logger.exception("panel join email send failed for %s", email)
    return {"ok": True}


@router.post("/join/confirm")
@limiter.limit("20/minute")
def confirm_panel_join(request: Request, body: TokenRequest, db: Session = Depends(get_db)):
    """Confirm a public signup: record consent, create the profile if needed,
    and hand back a durable panel session so the portal opens immediately.
    Idempotent — re-clicking the emailed link keeps working."""
    payload = ps.resolve_join_token(body.token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired confirmation link.",
        )
    profile = (
        db.query(PanelProfile)
        .filter(func.lower(PanelProfile.email) == payload["email"].lower())
        .first()
    )
    now = datetime.utcnow()
    if profile is None:
        profile = PanelProfile(email=payload["email"], created_at=now)
        db.add(profile)
    if not profile.panel_consent:
        profile.panel_consent = True
        profile.consent_at = now
    if not profile.first_name and payload["first_name"]:
        profile.first_name = payload["first_name"]
    if not profile.preferred_language:
        profile.preferred_language = payload["lang"]
    profile.last_active = now
    db.commit()
    db.refresh(profile)
    return {"token": ps.create_panel_session(profile.email)}


@router.post("/request-access")
@limiter.limit("5/minute")
def request_access(request: Request, body: RequestAccessRequest, db: Session = Depends(get_db)):
    """Re-email the durable 'manage your panel' link. Always 200 (no account
    enumeration) — only actually sends to a consented panelist."""
    profile = (
        db.query(PanelProfile)
        .filter(PanelProfile.email == body.email, PanelProfile.panel_consent.is_(True))
        .first()
    )
    if profile is not None:
        from app.services.email import send_panel_access_link
        lang = (body.lang or profile.preferred_language or "en")[:2]
        token = ps.create_panel_session(profile.email)
        try:
            send_panel_access_link(email=profile.email, token=token, lang=lang)
        except Exception:  # pragma: no cover — never leak send failures
            logger.exception("panel access link send failed for %s", profile.email)
    return {"ok": True}
