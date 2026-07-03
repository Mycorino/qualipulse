"""Model registry — pinned defaults, env overrides, and auto-latest fallback."""
import importlib

import pytest

from app.config import settings


@pytest.fixture
def fresh_registry(monkeypatch):
    """Reload ai_models with a cleared resolution cache for each test."""
    def _load():
        import app.services.ai_models as m
        importlib.reload(m)
        m._resolved.cache_clear()
        return m
    return _load


def test_pinned_defaults(fresh_registry, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_SONNET", "")
    monkeypatch.setattr(settings, "MODEL_OPUS", "")
    monkeypatch.setattr(settings, "MODEL_HAIKU", "")
    monkeypatch.setattr(settings, "MODEL_AUTO_LATEST", False)
    m = fresh_registry()
    assert m.sonnet() == "claude-sonnet-4-6"
    assert m.opus() == "claude-opus-4-8"
    assert m.haiku() == "claude-haiku-4-5"


def test_env_override(fresh_registry, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_SONNET", "claude-sonnet-9-9")
    monkeypatch.setattr(settings, "MODEL_AUTO_LATEST", False)
    m = fresh_registry()
    m._resolved.cache_clear()
    assert m.sonnet() == "claude-sonnet-9-9"


def test_auto_latest_falls_back_on_error(fresh_registry, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_SONNET", "")
    monkeypatch.setattr(settings, "MODEL_AUTO_LATEST", True)
    m = fresh_registry()
    m._resolved.cache_clear()
    # _latest_for_family swallows errors (e.g. no/invalid API key) and returns
    # the pinned fallback — resolution must never crash or return empty.
    monkeypatch.setattr(m, "_latest_for_family", lambda fam, fb: fb)
    assert m.sonnet() == "claude-sonnet-4-6"


def test_accessors_never_empty(fresh_registry, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_AUTO_LATEST", False)
    m = fresh_registry()
    m._resolved.cache_clear()
    assert all([m.sonnet(), m.opus(), m.haiku()])
