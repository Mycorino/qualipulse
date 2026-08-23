"""Structured logging configuration."""
import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

# Per-request correlation id, set by the request-id middleware in main.py.
# Defaults to "-" so log lines emitted outside a request (startup, background
# threads that don't set it) still format cleanly.
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    """Inject the current request id onto every log record as ``request_id``."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure JSON structured logging."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(request_id)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())
    root_logger.addHandler(handler)

    # Quieten noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # python_http_client (the SendGrid SDK transport) logs every request's
    # headers at INFO, which dumps the raw SendGrid API key into Cloud Run
    # logs on every send. Quieten it so credentials stay out of the logs.
    logging.getLogger("python_http_client").setLevel(logging.WARNING)
    logging.getLogger("sendgrid").setLevel(logging.WARNING)


logger = logging.getLogger("auto_interview")
