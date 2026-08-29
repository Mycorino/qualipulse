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
    assert m.sonnet() == "claude-sonnet-5"
    assert m.opus() == "claude-opus-4-8"
    assert m.haiku() == "claude-haiku-4-5"


def test_temperature_kwargs_guard():
    from app.services import ai_models

    # Older models get their tuned temperature.
    assert ai_models.temperature_kwargs("claude-sonnet-4-6", 0.4) == {"temperature": 0.4}
    assert ai_models.temperature_kwargs("claude-haiku-4-5", 0.1) == {"temperature": 0.1}
    # No-sampling generations get nothing.
    assert ai_models.temperature_kwargs("claude-sonnet-5", 0.4) == {}
    assert ai_models.temperature_kwargs("claude-opus-4-8", 0.3) == {}


def test_sampling_kwargs_pins_thinking_off_on_adaptive_default_models():
    """Legacy no-thinking call sites were tuned with tight max_tokens and
    latency budgets; a pin flip to an adaptive-by-default model must not
    silently turn thinking on for them."""
    from app.services import ai_models

    assert ai_models.sampling_kwargs("claude-sonnet-5", 0.4) == {
        "thinking": {"type": "disabled"}
    }
    assert ai_models.sampling_kwargs("claude-opus-5", 0.3) == {
        "thinking": {"type": "disabled"}
    }
    # Non-adaptive-default models keep the temperature behaviour.
    assert ai_models.sampling_kwargs("claude-sonnet-4-6", 0.4) == {"temperature": 0.4}
    assert ai_models.sampling_kwargs("claude-opus-4-8", 0.3) == {}
    # Fable/Mythos reject {"type": "disabled"}: omit everything.
    assert ai_models.sampling_kwargs("claude-fable-5", 0.4) == {}


def test_usage_logger_has_sonnet5_rates():
    from app.services.usage_logger import _claude_rates

    # Sonnet 5 is $2/$10 per MTok; the generic sonnet row stays $3/$15.
    assert _claude_rates("claude-sonnet-5") == (0.000002, 0.000010)
    assert _claude_rates("claude-sonnet-4-6") == (0.000003, 0.000015)
    assert _claude_rates("claude-opus-4-8") == (0.000005, 0.000025)


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
    assert m.sonnet() == "claude-sonnet-5"


def test_accessors_never_empty(fresh_registry, monkeypatch):
    monkeypatch.setattr(settings, "MODEL_AUTO_LATEST", False)
    m = fresh_registry()
    m._resolved.cache_clear()
    assert all([m.sonnet(), m.opus(), m.haiku()])
