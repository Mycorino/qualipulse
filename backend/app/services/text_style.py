"""House-style guards applied to model-generated, user-facing text.

Em/en dashes and double hyphens are banned from all product copy (see
CLAUDE.md, Copy Conventions). Prompts instruct the models; these helpers
guarantee it on whatever the model actually returns.
"""
from __future__ import annotations

import re

_BANNED_DASH_RE = re.compile(r"\s*(?:—|–|--)\s*")


def strip_banned_dashes(text: str) -> str:
    """Rewrite em/en dashes and ``--`` in prose into commas (or drop them
    after sentence punctuation, where they are redundant)."""
    if not text or not _BANNED_DASH_RE.search(text):
        return text
    text = re.sub(r"([,;:.!?…])\s*(?:—|–|--)\s*", r"\1 ", text)
    return _BANNED_DASH_RE.sub(", ", text)


def strip_banned_dashes_deep(value):
    """Apply :func:`strip_banned_dashes` to every string nested inside a
    JSON-like structure (dicts, lists, tuples). Non-string leaves and dict
    keys are left untouched."""
    if isinstance(value, str):
        return strip_banned_dashes(value)
    if isinstance(value, dict):
        return {k: strip_banned_dashes_deep(v) for k, v in value.items()}
    if isinstance(value, list):
        return [strip_banned_dashes_deep(v) for v in value]
    if isinstance(value, tuple):
        return tuple(strip_banned_dashes_deep(v) for v in value)
    return value
