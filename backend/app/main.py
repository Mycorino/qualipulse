import logging
import os
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
from app.logging_config import setup_logging, logger
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
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


# ── Global error handler ──────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "An unexpected error occurred."})


# ── Routers ───────────────────────────────────────────────────────────────────
from app.routers import (
    auth, projects, links, interview, export, audio,
    research_assistant, analysis, responses, coding, memos, billing, admin,
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(links.router)
app.include_router(interview.router)
app.include_router(export.router)
app.include_router(audio.router)
app.include_router(research_assistant.router)
app.include_router(analysis.router)
app.include_router(responses.router)
app.include_router(coding.router)
app.include_router(memos.router)
app.include_router(billing.router)
app.include_router(admin.router)


@app.get("/", tags=["health"])
async def health_check():
    return {"status": "ok", "service": "auto-interview-api", "env": settings.ENVIRONMENT}


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
