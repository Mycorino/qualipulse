"""Single source of truth for Claude model IDs.

Anthropic retires dated model snapshots periodically — one such retirement
(`claude-sonnet-4-20250514`) took the whole interview flow down. Hardcoding the
ID at every call site meant a 12-file change to recover. This module fixes that:

- One pinned default per family (sonnet / opus / haiku), known-good current IDs.
- Each is **overridable by env var** (`MODEL_SONNET`, `MODEL_OPUS`,
  `MODEL_HAIKU`) so a retirement is fixed by flipping a Cloud Run env var — no
  code change, no redeploy of the image.
- Optional **auto-latest** (`MODEL_AUTO_LATEST=1`): resolve the newest available
  model per family from the Models API at startup, falling back to the pinned
  value on any error.

Call sites use the accessors `sonnet()` / `opus()` / `haiku()`.

NOTE on auto-latest: it's off by default on purpose. A brand-new model can
change the request surface (recent Opus releases removed `temperature`,
`top_p`, and `budget_tokens` — passing them now 400s). Auto-upgrading blindly
can therefore break callers exactly the way a retirement does. Turn it on only
once you've confirmed the new models accept the params this codebase sends.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from app.config import settings

logger = logging.getLogger("auto_interview")

# Pinned, known-good current models (verified live). Keep these current.
_DEFAULTS = {
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-8",  # same $5/$25 pricing + request surface as 4.7
    "haiku": "claude-haiku-4-5",
}


def _latest_for_family(family: str, fallback: str) -> str:
    """Return the newest available model id whose id contains ``family``,
    per the Models API; ``fallback`` on any error or no match. The Models API
    only lists currently-available models, so a retired id can never be picked.
    """
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        candidates = [m for m in client.models.list() if family in m.id.lower()]
        if not candidates:
            return fallback
        # created_at is ISO-8601; lexical sort is chronological. Newest wins.
        newest = max(candidates, key=lambda m: getattr(m, "created_at", "") or "")
        return newest.id
    except Exception:  # pragma: no cover — never let model discovery break boot
        logger.warning("model auto-latest lookup failed for %s; using %s", family, fallback)
        return fallback


@lru_cache(maxsize=None)
def _resolved() -> dict[str, str]:
    """Resolve each family's model id once and cache it. Pinned default ←
    env override ← (optional) Models-API latest."""
    pins = {
        "sonnet": settings.MODEL_SONNET or _DEFAULTS["sonnet"],
        "opus": settings.MODEL_OPUS or _DEFAULTS["opus"],
        "haiku": settings.MODEL_HAIKU or _DEFAULTS["haiku"],
    }
    if settings.MODEL_AUTO_LATEST:
        for fam in pins:
            pins[fam] = _latest_for_family(fam, pins[fam])
    return pins


def sonnet() -> str:
    """Interview engine, analysis, quality, translation, etc."""
    return _resolved()["sonnet"]


def opus() -> str:
    """Research Copilot (adaptive thinking)."""
    return _resolved()["opus"]


def haiku() -> str:
    """Lightweight tasks — onboarding personalisation, name lookup, etc."""
    return _resolved()["haiku"]


# Model generations that REJECT non-default sampling params — passing
# `temperature` / `top_p` / `top_k` to these returns a 400. (Opus 4.7 removed
# them; Opus 4.8 keeps that surface; Sonnet 5 rejects non-default values.)
_NO_SAMPLING_MARKERS = (
    "opus-4-7",
    "opus-4-8",
    "sonnet-5",
    "fable",
    "mythos",
)


def temperature_kwargs(model_id: str, temperature: float) -> dict:
    """``{"temperature": X}`` for models that accept it, ``{}`` otherwise.

    Call sites splat this (``**ai_models.temperature_kwargs(model, 0.3)``)
    instead of passing ``temperature=`` directly, so flipping a model pin or
    enabling ``MODEL_AUTO_LATEST`` can never 400 an existing caller.
    """
    lowered = (model_id or "").lower()
    if any(marker in lowered for marker in _NO_SAMPLING_MARKERS):
        return {}
    return {"temperature": temperature}


def log_resolved() -> None:
    """Log the resolved model ids at startup (visibility + a paper trail of
    what auto-latest picked)."""
    r = _resolved()
    logger.info(
        "Claude models resolved: sonnet=%s opus=%s haiku=%s (auto_latest=%s)",
        r["sonnet"], r["opus"], r["haiku"], settings.MODEL_AUTO_LATEST,
    )
