"""Shared AI client factory.

Every Anthropic call goes through ``get_anthropic_client`` so no call can
hang without a timeout. Pass a custom ``timeout`` when an operation's
latency budget differs from the default (e.g. 10s for quick coaching
calls, 300s for streaming Copilot turns with adaptive thinking).

Both provider paths also run failures past ``ai_spend.note_provider_error``,
which raises an ops alarm when the error means our provider balance is
empty. That is the one signal about running out of credit that is never an
estimate, and these two functions are the only places every call passes
through.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger("auto_interview.clients")

DEFAULT_TIMEOUT_SECONDS = 120.0

T = TypeVar("T")


def _note(provider: str, label: str, exc: BaseException) -> None:
    """Hand the failure to the spend monitor. Never raises, never blocks the
    real error from propagating."""
    try:
        from app.services.ai_spend import note_provider_error

        note_provider_error(provider, label, exc)
    except Exception:  # pragma: no cover — monitoring must not break calls
        logger.exception("Provider error hook failed")


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

    An exhausted balance arrives as ``RateLimitError`` with code
    ``insufficient_quota``, which looks transient but is not: retrying it just
    burns three attempts and 1.5s on the interview's critical path. So it
    fails fast, and raises the ops alarm on the way out.
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
        except Exception as exc:
            from app.services.ai_spend import is_out_of_credit

            if is_out_of_credit(exc):
                _note("openai", label, exc)
                raise
            if not isinstance(exc, transient):
                raise
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


class _WatchedStreamManager:
    """Wraps the context manager returned by ``client.messages.stream``.

    The request is made in ``__enter__``, which is where a billing refusal
    surfaces (the 400 comes back before the first token). Everything else is
    delegated untouched.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def __enter__(self):
        try:
            return self._inner.__enter__()
        except Exception as exc:
            _note("anthropic", "messages.stream", exc)
            raise

    def __exit__(self, *exc_info):
        return self._inner.__exit__(*exc_info)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _WatchedMessages:
    """Thin proxy over ``client.messages`` that watches ``create`` and
    ``stream`` for billing refusals. Every other attribute (``count_tokens``,
    ``batches``, ``with_raw_response``, …) passes straight through, so this
    is invisible to callers."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def create(self, *args, **kwargs):
        try:
            return self._inner.create(*args, **kwargs)
        except Exception as exc:
            _note("anthropic", "messages.create", exc)
            raise

    def stream(self, *args, **kwargs):
        return _WatchedStreamManager(self._inner.stream(*args, **kwargs))

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


def get_anthropic_client(timeout: float = DEFAULT_TIMEOUT_SECONDS):
    # Lazy imports keep test environments AI-free (mirrors the existing
    # lazy-import convention in copilot.py / quality.py / translation.py).
    import anthropic
    import httpx

    from app.config import settings

    client = anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=httpx.Timeout(timeout),
    )
    # ``messages`` is a cached_property, so assigning here just seeds the
    # instance dict — the SDK never looks at the class attribute again.
    # Only the first-party ``client.messages`` surface is wrapped; nothing
    # in this codebase calls ``client.beta.messages``.
    try:
        client.messages = _WatchedMessages(client.messages)
    except Exception:  # pragma: no cover — never fail client construction
        logger.exception("Could not attach the billing watcher to the Anthropic client")
    return client
