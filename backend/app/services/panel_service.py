"""Panel enrichment service — durable panel access tokens, answer validation,
localisation, and completeness scoring.

Two token types authorise enrichment writes:
  - ``participant_session`` (2h) — issued by the interview magic-link flow;
    lets a panelist enrich right after their interview.
  - ``panel_session`` (~90d) — the durable token behind the emailed
    "manage your panel" link, so they can return and keep adding over time.
Both are plain JWTs signed with SECRET_KEY (no DB row).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models.panel import PanelAttribute, PanelAnswer, PanelProfile

ALGORITHM = "HS256"
PANEL_SESSION_DAYS = 90
PANEL_JOIN_HOURS = 48
SUPPORTED_LANGS = {"en", "fr", "de", "es", "it", "pt"}


# ── Durable panel-session token ──────────────────────────────────────────────

def create_panel_session(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=PANEL_SESSION_DAYS)
    return jwt.encode(
        {"email": email, "type": "panel_session", "exp": expire},
        settings.SECRET_KEY, algorithm=ALGORITHM,
    )


def resolve_panel_email(token: str | None) -> str | None:
    """Return the email a token authorises, accepting either a long-lived
    ``panel_session`` or a still-valid interview ``participant_session``.
    """
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") not in ("panel_session", "participant_session"):
        return None
    if payload.get("type") == "participant_session" and not payload.get("verified"):
        return None
    email = payload.get("email")
    return email if isinstance(email, str) and email else None


# ── Recontact opt-out token ──────────────────────────────────────────────────
# Signed link embedded in every study-invite email. Long-lived on purpose:
# GDPR says withdrawing consent must stay as easy as giving it, so the link
# in a months-old email should still work.

PANEL_OPTOUT_DAYS = 365


def create_optout_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=PANEL_OPTOUT_DAYS)
    return jwt.encode(
        {"email": email, "type": "panel_optout", "exp": expire},
        settings.SECRET_KEY, algorithm=ALGORITHM,
    )


def resolve_optout_token(token: str | None) -> str | None:
    """Return the email a valid panel_optout token belongs to."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != "panel_optout":
        return None
    email = payload.get("email")
    return email if isinstance(email, str) and email else None


# ── Public join (double opt-in) token ────────────────────────────────────────

def create_join_token(email: str, first_name: str | None, lang: str) -> str:
    """Signed confirmation token behind the 'confirm your spot' email sent to
    a public panel signup. Consent is only recorded when this comes back."""
    expire = datetime.now(timezone.utc) + timedelta(hours=PANEL_JOIN_HOURS)
    return jwt.encode(
        {
            "email": email,
            "first_name": first_name or "",
            "lang": lang,
            "type": "panel_join",
            "exp": expire,
        },
        settings.SECRET_KEY, algorithm=ALGORITHM,
    )


def resolve_join_token(token: str | None) -> dict | None:
    """Return {email, first_name, lang} for a valid panel_join token."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != "panel_join":
        return None
    email = payload.get("email")
    if not isinstance(email, str) or not email:
        return None
    lang = payload.get("lang")
    return {
        "email": email,
        "first_name": payload.get("first_name") or None,
        "lang": lang if lang in SUPPORTED_LANGS else "en",
    }


# ── Localisation ─────────────────────────────────────────────────────────────

def _pick(label_i18n: dict, lang: str) -> str:
    return label_i18n.get(lang) or label_i18n.get("en") or next(iter(label_i18n.values()), "")


def localize_attribute(attr: PanelAttribute, lang: str) -> dict:
    """Render one catalogue row for the client in the requested locale."""
    lang = lang if lang in SUPPORTED_LANGS else "en"
    options = json.loads(attr.options) if attr.options else []
    return {
        "id": attr.id,
        "category": attr.category,
        "type": attr.type,
        "is_sensitive": attr.is_sensitive,
        "priority": attr.priority,
        "label": _pick(json.loads(attr.label_i18n), lang),
        "options": [
            {"value": o["value"], "label": _pick(o.get("label_i18n", {}), lang)}
            for o in options
        ],
    }


# ── Answer validation + upsert ───────────────────────────────────────────────

def validate_value(attr: PanelAttribute, value) -> tuple[bool, object]:
    """Validate a submitted value against the attribute type. Returns
    (ok, normalised_value)."""
    options = json.loads(attr.options) if attr.options else []
    allowed = {o["value"] for o in options}
    if attr.type == "bool":
        return (isinstance(value, bool), value)
    if attr.type in ("single", "scale"):
        return (isinstance(value, str) and value in allowed, value)
    if attr.type == "multi":
        if not isinstance(value, list):
            return (False, value)
        cleaned = [v for v in value if isinstance(v, str) and v in allowed]
        return (len(cleaned) == len(value) and len(value) > 0, cleaned)
    return (False, value)


def upsert_answers(
    db: Session, profile: PanelProfile, answers: list[dict]
) -> tuple[int, list[str]]:
    """Upsert a batch of {attribute_id, value}. Ignores unknown/inactive
    attributes and rejects sensitive ones without consent. Returns
    (saved_count, rejected_attribute_ids).

    Uses an atomic INSERT … ON CONFLICT DO UPDATE so concurrent saves for the
    same (profile, attribute) — easy to trigger when a participant taps fast —
    can't collide on the unique constraint.
    """
    catalog = {a.id: a for a in db.query(PanelAttribute).filter(PanelAttribute.active.is_(True)).all()}
    saved = 0
    rejected: list[str] = []
    now = datetime.utcnow()

    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert
    else:  # sqlite (dev/tests) — same on_conflict API
        from sqlalchemy.dialects.sqlite import insert as _insert

    for item in answers:
        attr = catalog.get(item.get("attribute_id"))
        if attr is None:
            rejected.append(item.get("attribute_id"))
            continue
        if attr.is_sensitive and not profile.sensitive_data_consent:
            rejected.append(attr.id)
            continue
        ok, normalised = validate_value(attr, item.get("value"))
        if not ok:
            rejected.append(attr.id)
            continue
        encoded = json.dumps(normalised, ensure_ascii=False)
        stmt = _insert(PanelAnswer).values(
            profile_id=profile.id, attribute_id=attr.id, value=encoded,
            created_at=now, updated_at=now,
        ).on_conflict_do_update(
            index_elements=["profile_id", "attribute_id"],
            set_={"value": encoded, "updated_at": now},
        )
        db.execute(stmt)
        saved += 1

    profile.last_active = now
    db.commit()
    # Core inserts bypass the ORM identity map — expire the loaded relationship
    # so completeness() (which reads profile.answers) sees the new rows.
    db.expire(profile, ["answers"])
    return saved, rejected


# ── Completeness (priority-weighted) ─────────────────────────────────────────

def completeness(db: Session, profile: PanelProfile) -> dict:
    """How much of the (visible) catalogue the panelist has answered, weighted
    by priority. Sensitive attributes only count toward the denominator once
    consent is given."""
    attrs = db.query(PanelAttribute).filter(PanelAttribute.active.is_(True)).all()
    if not profile.sensitive_data_consent:
        attrs = [a for a in attrs if not a.is_sensitive]
    total = sum(max(a.priority, 1) for a in attrs)
    answered_ids = {a.attribute_id for a in profile.answers}
    done = sum(max(a.priority, 1) for a in attrs if a.id in answered_ids)
    pct = round(100 * done / total) if total else 0
    return {
        "answered_count": len([a for a in attrs if a.id in answered_ids]),
        "total_count": len(attrs),
        "percent": pct,
    }


def current_answers(profile: PanelProfile) -> dict:
    """Map of attribute_id -> decoded value for the panelist."""
    out = {}
    for a in profile.answers:
        try:
            out[a.attribute_id] = json.loads(a.value)
        except (ValueError, TypeError):
            out[a.attribute_id] = a.value
    return out
