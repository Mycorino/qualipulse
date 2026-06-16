"""Shared AI client factory.

Every Anthropic call goes through ``get_anthropic_client`` so no call can
hang without a timeout. Pass a custom ``timeout`` when an operation's
latency budget differs from the default (e.g. 10s for quick coaching
calls, 300s for streaming Copilot turns with adaptive thinking).
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger("auto_interview.clients")

DEFAULT_TIMEOUT_SECONDS = 120.0

T = TypeVar("T")


def call_openai_with_retries(
    fn: Callable[[], T],
    *,
    label: str,
    attempts: int = 3,
    base_delay: float = 0.5,
) -> T:
    """Run an OpenAI call, retrying transient failures with exponential backoff.

    Only retries on transient errors (timeout / connection / rate-limit / 5xx) —
    client errors like 400 (malformed audio) fail fast. STT and TTS sit on the
    critical path of every interview turn, so a single flaky OpenAI response
    shouldn't break the turn.
    """
    import openai

    transient = (
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.RateLimitError,
        openai.InternalServerError,
    )
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except transient as exc:
            last_exc = exc
            if attempt == attempts:
                break
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "%s transient failure (attempt %d/%d): %s — retrying in %.1fs",
                label, attempt, attempts, exc, delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


def get_anthropic_client(timeout: float = DEFAULT_TIMEOUT_SECONDS):
    # Lazy imports keep test environments AI-free (mirrors the existing
    # lazy-import convention in copilot.py / quality.py / translation.py).
    import anthropic
    import httpx

    from app.config import settings

    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=httpx.Timeout(timeout),
    )
