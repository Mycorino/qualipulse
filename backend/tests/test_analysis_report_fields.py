"""Unit tests for the analysis quote verifier over the report v2 fields.

`_verify_report_quotes` must now walk theme quotes AND persona anchor quotes AND
journey stage quotes, so hallucinated evidence in the new sections is flagged
(verified=false) exactly like theme quotes — the traceability guarantee is what
separates these exhibits from decoration.
"""
from types import SimpleNamespace as NS

import pytest

from app.services.analysis import _verify_report_quotes


def _participant(text: str):
    return NS(turns=[NS(response_transcript=text)])


def test_verifier_flags_persona_and_journey_quotes():
    parts = [
        _participant("i always check the tracking page twice a day"),          # P1
        _participant("if the package is late and nobody tells me i'm done"),   # P2
    ]
    report = {
        "themes": [{"quotes": [
            {"text": "i always check the tracking page", "participant_identifier": "P1"},
        ]}],
        "personas": [
            {"anchor_quote": {"text": "nobody tells me", "participant_identifier": "P2"}},
            {"anchor_quote": {"text": "this was never said", "participant_identifier": "P1"}},
        ],
        "journey": {"stages": [
            {"quote": {"text": "tracking page twice a day", "participant_identifier": "P1"}},
            {"quote": {"text": "fabricated stage quote", "participant_identifier": "P2"}},
        ]},
    }

    verified, total = _verify_report_quotes(report, parts)

    assert total == 5
    assert verified == 3
    assert report["themes"][0]["quotes"][0]["verified"] is True
    assert report["personas"][0]["anchor_quote"]["verified"] is True
    assert report["personas"][1]["anchor_quote"]["verified"] is False
    assert report["journey"]["stages"][0]["quote"]["verified"] is True
    assert report["journey"]["stages"][1]["quote"]["verified"] is False


def test_verifier_handles_missing_personas_and_journey():
    """Legacy reports with no personas/journey keys must not error."""
    parts = [_participant("hello world this is a transcript")]
    report = {"themes": [{"quotes": [
        {"text": "hello world", "participant_identifier": "P1"},
    ]}]}
    verified, total = _verify_report_quotes(report, parts)
    assert (verified, total) == (1, 1)


def test_verifier_tolerates_non_dict_shapes():
    parts = [_participant("a b c")]
    report = {
        "themes": [],
        "personas": [{"anchor_quote": None}, "not-a-dict"],
        "journey": {"stages": ["nope", {"quote": None}]},
    }
    # Nothing verifiable, nothing raised.
    assert _verify_report_quotes(report, parts) == (0, 0)


# ── Opus 4.8 synthesis helpers ──────────────────────────────────────────────
# Adaptive thinking puts a thinking block before the text block, so the report
# JSON must be pulled from the text block, not content[0]. These lock that in.
from app.services.analysis import (  # noqa: E402
    _parse_report,
    _raise_on_bad_stop,
    _is_output_format_error,
    _REPORT_SCHEMA,
    ANALYSIS_SYSTEM_PROMPT,
)


def test_parse_report_skips_thinking_block():
    resp = NS(content=[
        NS(type="thinking", text=""),          # adaptive-thinking block first
        NS(type="text", text='{"summary": "ok", "themes": []}'),
    ], stop_reason="end_turn")
    assert _parse_report(resp) == {"summary": "ok", "themes": []}


def test_parse_report_strips_fences_fallback():
    # No-structured-output retry path may fence — belt-and-suspenders.
    resp = NS(content=[NS(type="text", text='```json\n{"summary": "x"}\n```')])
    assert _parse_report(resp) == {"summary": "x"}


def test_raise_on_bad_stop():
    for stop in ("max_tokens", "refusal"):
        with pytest.raises(ValueError):
            _raise_on_bad_stop(NS(stop_reason=stop))
    _raise_on_bad_stop(NS(stop_reason="end_turn"))  # no raise


def test_output_format_error_heuristic():
    assert _is_output_format_error(Exception("invalid json_schema in output_config"))
    assert not _is_output_format_error(Exception("connection reset by peer"))


def test_report_schema_is_structured_output_safe():
    import json as _json

    def _walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                # structured outputs require additionalProperties:false + required
                assert node.get("additionalProperties") is False
                assert set(node["required"]) == set(node["properties"].keys())
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    _walk(_REPORT_SCHEMA)
    # `verified` is added post-generation by the verifier — never in the model schema.
    assert "verified" not in _json.dumps(_REPORT_SCHEMA)


def test_system_prompt_keeps_reasoning_out_of_visible_answer():
    assert "ONE valid JSON object" in ANALYSIS_SYSTEM_PROMPT
    assert "thinking" in ANALYSIS_SYSTEM_PROMPT.lower()
