"""Client-side error reporting.

The frontend has no error-tracking SDK (VITE_* env vars are baked at
build time and the Cloud Build pipeline injects no DSN), so the SPA
POSTs uncaught errors here instead. Logging at ERROR level routes them
into the backend's existing Sentry integration and Cloud Logging, which
is all GA observability needs. Public endpoint: hard rate limit, strict
payload caps, and no echo of the payload in the response.
"""

import logging

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field

from app.limiter import limiter

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
