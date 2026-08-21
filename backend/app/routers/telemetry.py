"""Client-side error + product-analytics ingestion.

The frontend has no error-tracking SDK (VITE_* env vars are baked at
build time and the Cloud Build pipeline injects no DSN), so the SPA
POSTs uncaught errors here instead. Logging at ERROR level routes them
into the backend's existing Sentry integration and Cloud Logging, which
is all GA observability needs. Public endpoint: hard rate limit, strict
payload caps, and no echo of the payload in the response.

``/telemetry/event`` is the first-party alternative to shipping a
third-party analytics SDK: the SPA POSTs a small, closed set of funnel
events here and they are re-emitted through ``services.analytics`` so
homepage traffic lands in the *same* ``analytics event=...`` log stream
as the server-side milestones (signup, study_created, paid_converted).
No cookies, no third-party host, no CSP change (``connect-src 'self'``
already covers it), and no consent banner obligation.
"""

import hashlib
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.limiter import limiter
from app.models.web_event import WebEvent
from app.services.analytics import emit_event

logger = logging.getLogger("auto_interview.client")

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class ClientErrorReport(BaseModel):
    message: str = Field(max_length=2000)
    stack: str | None = Field(default=None, max_length=8000)
    url: str | None = Field(default=None, max_length=500)
    user_agent: str | None = Field(default=None, max_length=500)
    # "error" (window.onerror) or "unhandledrejection"
    kind: str = Field(default="error", max_length=32)


@router.post("/client-error", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
def report_client_error(
    request: Request,
    body: ClientErrorReport,
) -> None:
    logger.error(
        "client_error kind=%s url=%s ua=%s message=%s\n%s",
        body.kind,
        body.url or "",
        (body.user_agent or "")[:200],
        body.message,
        body.stack or "",
    )


# --- Product analytics -------------------------------------------------

# Closed catalogue. An open endpoint that writes arbitrary event names
# into the log stream is a log-spam vector and wrecks the cardinality of
# any dashboard built on top, so unknown names are dropped silently
# (204, same as success — never tell a prober what exists).
_ALLOWED_EVENTS = frozenset(
    {
        "page_view",
        "cta_signup_click",
        "pricing_viewed",
        "pricing_interval_toggled",
        "newsletter_submit",
        "analysis_viewed",
    }
)

# Paths are logged verbatim, so only the public marketing/auth/legal
# surface is allowed through, by allowlist rather than by pattern: every
# authenticated route carries a study, survey, or participant id, and a
# pattern loose enough to accept "/blog/some-slug" is also loose enough to
# accept "/studies/<uuid>". Mirrors PUBLIC_PAGEVIEW_PATHS in App.tsx.
_PUBLIC_PATHS = frozenset(
    {
        "/",
        "/login",
        "/signup",
        "/forgot-password",
        "/reset-password",
        "/terms",
        "/privacy",
        "/dpa",
        "/subprocessors",
        "/participant-notice",
        "/ai-use-policy",
        "/retention-policy",
        "/blog",
    }
)


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith("/blog/")

# Cheap, deliberately shallow bot filter. Real crawlers execute no JS at
# all; this only catches the headless/preview agents that do.
_BOT_RE = re.compile(
    r"bot|crawler|spider|crawling|headless|phantom|puppeteer|playwright|lighthouse",
    re.IGNORECASE,
)

# Note the omissions: "=", "?" and "&" are NOT allowed. Without that, a
# caller could smuggle a second `event=...` token into a log line and
# poison any count built by grepping the stream. Dropping them also strips
# referrer query strings, which is the privacy-preserving default anyway.
_SAFE_TOKEN_RE = re.compile(r"[^A-Za-z0-9 ._\-/:%+@]")


def _clean(value: str | None, limit: int) -> str | None:
    """Strip anything that could forge a log line, then truncate."""
    if not value:
        return None
    text = _SAFE_TOKEN_RE.sub("", value).strip()
    return text[:limit] or None


def _visitor_hash(request: Request) -> str:
    """A daily-rotating, non-reversible visitor id.

    ``sha256(secret | utc-date | ip | user-agent)`` truncated to 16 hex
    chars. Rotating the date daily means the id cannot be used to follow
    someone across days, and nothing derived from the IP is ever stored,
    which is what keeps this inside the CNIL audience-measurement
    exemption (no cookie, no consent banner).
    """
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = hashlib.sha256(
        f"{settings.SECRET_KEY}|{day}|{ip}|{ua}".encode("utf-8", "replace")
    ).hexdigest()
    return digest[:16]


class ClientEvent(BaseModel):
    """One funnel event fired by the SPA.

    Deliberately a fixed schema rather than a free-form props bag: every
    field is bounded and sanitised before it reaches the log stream.
    """

    event: str = Field(max_length=64)
    # Public route the event happened on ("/", "/signup", "/blog/slug").
    path: str | None = Field(default=None, max_length=200)
    # Which instance of a repeated control fired it ("hero", "nav", ...).
    location: str | None = Field(default=None, max_length=64)
    referrer: str | None = Field(default=None, max_length=300)
    utm_source: str | None = Field(default=None, max_length=100)
    utm_medium: str | None = Field(default=None, max_length=100)
    utm_campaign: str | None = Field(default=None, max_length=100)
    lang: str | None = Field(default=None, max_length=5)


@router.post("/event", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("60/minute")
def report_client_event(
    request: Request,
    body: ClientEvent,
    db: Session = Depends(get_db),
) -> None:
    """Ingest one anonymous funnel event from the marketing site.

    Written twice on purpose: to the log stream (grep-able alongside the
    server-side milestones, and the thing that works even if the DB is
    down) and to ``web_events`` (permanent, aggregated by the admin
    Traffic tab, where Cloud Logging would have dropped it after 30 days).
    """
    if body.event not in _ALLOWED_EVENTS:
        return

    ua = request.headers.get("user-agent", "")
    if _BOT_RE.search(ua):
        return

    path = _clean(body.path, 200)
    if path and not _is_public_path(path):
        # Authenticated deep link: keep the event, drop the identifiers.
        path = "/redacted"

    fields = {
        "visitor": _visitor_hash(request),
        "path": path,
        "location": _clean(body.location, 64),
        "referrer": _clean(body.referrer, 300),
        "utm_source": _clean(body.utm_source, 100),
        "utm_medium": _clean(body.utm_medium, 100),
        "utm_campaign": _clean(body.utm_campaign, 100),
        "lang": _clean(body.lang, 5),
    }

    emit_event(body.event, source="web", **fields)

    try:
        db.add(WebEvent(event=body.event, **fields))
        db.commit()
    except Exception:  # noqa: BLE001 — analytics must never break a page.
        db.rollback()
        logger.exception("web_event persist failed")
