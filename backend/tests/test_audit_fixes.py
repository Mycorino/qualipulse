"""Tests for the product-audit fixes.

Covers the pure, AI-free helpers introduced or hardened during the audit:
- CSV formula-injection escaping in the transcript export
- verbatim quote verification in the analysis pipeline
- the follow-up depth cap constant
"""

from app.routers.export import _csv_safe
from app.services.analysis import _normalize_for_match, _verify_report_quotes
from app.services import interview_engine


# ── CSV formula-injection escaping ────────────────────────────────────────────

def test_csv_safe_escapes_formula_triggers():
    for payload in ("=1+1", "+cmd", "-2+3", "@SUM(A1)", "\tTAB", "\rCR"):
        out = _csv_safe(payload)
        assert out.startswith("'"), f"{payload!r} was not escaped"
        assert out == "'" + payload


def test_csv_safe_leaves_normal_text_untouched():
    for benign in ("Alice", "alice@example.com", "I love it", "", "3 apples"):
        assert _csv_safe(benign) == benign


def test_csv_safe_handles_none():
    assert _csv_safe(None) == ""


# ── Quote verification against transcripts ────────────────────────────────────

class _FakeTurn:
    def __init__(self, turn_index, response):
        self.turn_index = turn_index
        self.response_transcript = response


class _FakeParticipant:
    def __init__(self, turns):
        self.turns = turns


def _participants():
    return [
        _FakeParticipant([
            _FakeTurn(0, "I switched because the price kept going up."),
            _FakeTurn(1, "The app was slow on my phone."),
        ]),
        _FakeParticipant([
            _FakeTurn(0, "Trust is the main thing for me."),
        ]),
    ]


def test_verify_report_flags_verbatim_and_hallucinated_quotes():
    report = {
        "themes": [
            {
                "quotes": [
                    {"text": "the price kept going up", "participant_identifier": "P1"},
                    {"text": "Trust is the main thing", "participant_identifier": "P2"},
                    {"text": "this sentence was never said", "participant_identifier": "P1"},
                ]
            }
        ]
    }
    verified, total = _verify_report_quotes(report, _participants())
    assert total == 3
    assert verified == 2
    quotes = report["themes"][0]["quotes"]
    assert quotes[0]["verified"] is True
    assert quotes[1]["verified"] is True
    assert quotes[2]["verified"] is False


def test_verify_report_matches_across_participants_when_identifier_wrong():
    # Even if the model mis-attributes the identifier, a genuinely verbatim
    # quote is still verified via the all-transcripts fallback.
    report = {"themes": [{"quotes": [
        {"text": "The app was slow on my phone.", "participant_identifier": "P2"},
    ]}]}
    verified, total = _verify_report_quotes(report, _participants())
    assert (verified, total) == (1, 1)


def test_verify_report_handles_missing_and_empty():
    assert _verify_report_quotes({}, _participants()) == (0, 0)
    report = {"themes": [{"quotes": [{"text": ""}]}]}
    verified, total = _verify_report_quotes(report, _participants())
    assert (verified, total) == (0, 1)
    assert report["themes"][0]["quotes"][0]["verified"] is False


def test_normalize_for_match_is_lenient_on_punctuation():
    a = _normalize_for_match("It’s  GREAT — really.")
    b = _normalize_for_match("it's great - really.")
    assert a == b


# ── Follow-up depth cap ───────────────────────────────────────────────────────

def test_followup_cap_constant_is_sane():
    assert isinstance(interview_engine.MAX_FOLLOWUPS_PER_QUESTION, int)
    assert 1 <= interview_engine.MAX_FOLLOWUPS_PER_QUESTION <= 5
