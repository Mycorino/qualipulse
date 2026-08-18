import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from fastapi import Depends, HTTPException
from app.config import settings
from app.database import Base, engine
from app.dependencies import get_db
from app.limiter import limiter
from app.logging_config import setup_logging, logger, request_id_ctx
import app.models  # noqa: F401 — register all models with Base metadata

# Initialise logging before anything else
setup_logging("DEBUG" if settings.DEBUG else "INFO")

# Sentry (optional — only active if SENTRY_DSN is set)
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        traces_sample_rate=0.1,
    )
    logger.info("Sentry initialised (env=%s)", settings.ENVIRONMENT)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    Base.metadata.create_all(bind=engine)
    if not settings.R2_ACCOUNT_ID:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Credits-system bootstrap: keep the plans catalogue in sync with code,
    # then ensure every existing Company has a WorkspaceSubscription on the
    # appropriate legacy plan. Both are idempotent and cheap.
    try:
        from app.database import SessionLocal
        from app.services.billing_service import (
            backfill_legacy_subscriptions,
            ensure_plans_seeded,
        )
        with SessionLocal() as bootstrap_db:
            ensure_plans_seeded(bootstrap_db)
            created = backfill_legacy_subscriptions(bootstrap_db)
            if created:
                logger.info("Backfilled %d legacy subscription rows", created)
    except Exception:  # pragma: no cover — never block startup on billing
        logger.exception("Billing bootstrap failed; continuing with degraded billing")

    # Resolve + log the Claude model ids (and warn loudly if a configured model
    # is unavailable — catches a retirement at deploy, not via a participant 500).
    # Runs in a background thread: three sequential Anthropic round trips were
    # gating every cold start, and the check is log-only.
    def _validate_models() -> None:
        try:
            from app.services import ai_models
            ai_models.log_resolved()
            if settings.ANTHROPIC_API_KEY:
                import anthropic
                _client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
                for _mid in {ai_models.sonnet(), ai_models.opus(), ai_models.haiku()}:
                    try:
                        _client.models.retrieve(_mid)
                    except Exception:
                        logger.error("CONFIGURED CLAUDE MODEL UNAVAILABLE: %s — set MODEL_* env to a valid id", _mid)
        except Exception:  # pragma: no cover — never block startup on model checks
            logger.exception("Model resolution/validation failed; continuing")

    threading.Thread(target=_validate_models, daemon=True, name="model-check").start()

    # Panel enrichment: sync the profiling-attribute catalogue (idempotent).
    try:
        from app.database import SessionLocal
        from app.services.panel_catalog import ensure_attributes_seeded
        with SessionLocal() as bootstrap_db:
            ensure_attributes_seeded(bootstrap_db)
    except Exception:  # pragma: no cover — never block startup on the catalogue
        logger.exception("Panel catalogue seed failed; continuing")

    logger.info("AutoInterview API starting (env=%s)", settings.ENVIRONMENT)
    yield
    logger.info("AutoInterview API shutting down")


app = FastAPI(
    title="AutoInterview API",
    version="0.1.0",
    lifespan=lifespan,
    # Hide docs in production
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

# ── Rate limiter ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# ── CORS ─────────────────────────────────────────────────────────────────────
_cors_origins = settings.allowed_origins_list
if settings.is_production and _cors_origins == ["*"]:
    logger.warning(
        "CORS: wildcard origin '*' is not safe with allow_credentials in production. "
        "Blocking all cross-origin requests as a safe default. "
        "Set ALLOWED_ORIGINS to explicit origins."
    )
    _cors_origins = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security headers ──────────────────────────────────────────────────────────
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # JSON / audio responses get a deny-everything CSP, which neutralises any
    # reflected-content injection if a response is ever coerced into being
    # rendered. (The SPA's real CSP lives in the frontend nginx config.)
    # The report.html exports are the one HTML surface the API serves directly
    # (e.g. the public shared report) — they need their inline <style> blocks
    # and the onclick="window.print()" toolbar handler, nothing else. The
    # sha256 hash is base64(sha256("window.print()")); keep it in sync with
    # the frontend nginx CSP and services/report_export.py.
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("text/html"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "script-src 'unsafe-hashes' 'sha256-MguIPR6qNR8D3B+eAlK+bIRTZe8t3wkOY4B/56Me9FU='; "
            "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
        )
    else:
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
    if settings.is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Request size limit ────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = settings.MAX_AUDIO_SIZE_MB * 1024 * 1024

@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_UPLOAD_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request too large. Max size is {settings.MAX_AUDIO_SIZE_MB}MB."},
        )
    return await call_next(request)


# ── Request ID correlation ────────────────────────────────────────────────────
# Defined last so it is the OUTERMOST middleware (Starlette runs the
# most-recently-added middleware first) — the id is then set for every other
# middleware, the route, and the response header on all code paths.
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    incoming = request.headers.get("X-Request-ID")
    request_id = (incoming or uuid.uuid4().hex)[:64]
    token = request_id_ctx.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_ctx.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


# ── Routers ───────────────────────────────────────────────────────────────────
from app.routers import (
    auth, projects, links, interview, export, audio, files,
    analysis, responses, coding, memos, billing, admin, affiliate, blog,
    templates, team, surveys, public_surveys, studies, copilot,
    scheduled_emails, panel, synthesis, telemetry, seo,
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(links.router)
app.include_router(interview.router)
app.include_router(export.router)
app.include_router(audio.router)
app.include_router(files.router)
app.include_router(analysis.router)
app.include_router(responses.router)
app.include_router(coding.router)
app.include_router(memos.router)
app.include_router(billing.router)
app.include_router(affiliate.router)
app.include_router(admin.router)
app.include_router(blog.router)
app.include_router(templates.router)
app.include_router(team.router)
app.include_router(surveys.router)
app.include_router(public_surveys.router)
app.include_router(studies.router)
app.include_router(copilot.router)
app.include_router(synthesis.router)
app.include_router(scheduled_emails.router)
app.include_router(panel.router)
app.include_router(telemetry.router)
app.include_router(seo.router)


@app.get("/", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "auto-interview-api", "env": settings.ENVIRONMENT}


@app.get("/health", tags=["health"])
def deep_health_check(db=Depends(get_db)):
    """Deep health check — verifies the database is reachable."""
    from sqlalchemy import text

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("Health check DB probe failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})
    return {"status": "ok", "database": "ok", "env": settings.ENVIRONMENT}


@app.get("/reports/{share_token}", tags=["public"])
def get_shared_report(share_token: str, db=Depends(get_db)):
    """Public read-only view of a shared analysis report — no auth required."""
    from app.models.interview import ProjectAnalysis
    import json as _json
    analysis = db.query(ProjectAnalysis).filter(
        ProjectAnalysis.share_token == share_token,
        ProjectAnalysis.status == "ready",
    ).first()
    if analysis is None:
        raise HTTPException(status_code=404, detail="Report not found or link has been revoked.")
    return {
        "project_name": analysis.project.name if analysis.project else None,
        "participant_count": analysis.participant_count,
        "generated_at": analysis.generated_at.isoformat() if analysis.generated_at else None,
        "report": _json.loads(analysis.report) if analysis.report else None,
    }


@app.get("/reports/{share_token}/report.html", tags=["public"])
def get_shared_report_html(share_token: str, db=Depends(get_db)):
    """Print/PDF-ready standalone HTML of a shared report — no auth required.

    Public variant: the participant appendix (demographics + quality labels)
    is stripped; quotes keep the attribution the researcher chose to share.
    """
    from fastapi.responses import HTMLResponse

    from app.models.interview import Participant, ProjectAnalysis
    from app.services.report_export import render_analysis_report_html

    analysis = db.query(ProjectAnalysis).filter(
        ProjectAnalysis.share_token == share_token,
        ProjectAnalysis.status == "ready",
    ).first()
    if analysis is None or analysis.project is None:
        raise HTTPException(status_code=404, detail="Report not found or link has been revoked.")

    participants = (
        db.query(Participant)
        .filter(
            Participant.project_id == analysis.project_id,
            Participant.status == "completed",
        )
        .all()
    )
    html_doc = render_analysis_report_html(
        analysis.project, analysis, participants, annotations=[], include_appendix=False
    )
    return HTMLResponse(content=html_doc)
