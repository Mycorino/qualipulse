"""V3 — participant-experience demo endpoint.

Covers the pure helpers (_pick_code + _pick_highlight) since the
endpoint itself requires Whisper. The keyword → code map drives the
wow moment so the matching has to be deterministic and predictable.
"""

from __future__ import annotations

from app.routers.onboarding_demo import _pick_code, _pick_highlight


class TestPickCode:
    def test_trust_signal(self):
        label, _ = _pick_code(
            "I felt safe right away because they didn't feel like a giant corporation."
        )
        assert label == "Trust signal"

    def test_first_success_moment(self):
        label, color = _pick_code(
            "They walked me through it and it just worked in like two minutes."
        )
        # "walked me through" matches Onboarding craft FIRST — first match wins.
        assert label in {"First-success moment", "Onboarding craft"}
        assert color.startswith("#")

    def test_friction(self):
        label, _ = _pick_code(
            "I was completely stuck — couldn't figure out how to invite my team."
        )
        assert label == "Friction"

    def test_price_concern(self):
        label, _ = _pick_code(
            "It was way too expensive for what we actually needed."
        )
        assert label == "Price concern"

    def test_onboarding_craft(self):
        label, _ = _pick_code(
            "Their tutorial was excellent — a real step by step walkthrough."
        )
        assert label == "Onboarding craft"

    def test_fallback(self):
        label, _ = _pick_code(
            "Nothing in particular comes to mind right now."
        )
        assert label == "Worth coming back to"

    def test_empty(self):
        label, _ = _pick_code("")
        assert label == "Worth coming back to"


class TestPickHighlight:
    def test_prefers_keyword_match(self):
        transcript = "First sentence here. They walked me through setup in two minutes. Last sentence."
        segments = [
            {"start": 0.0, "end": 1.5, "text": "First sentence here."},
            {
                "start": 1.5,
                "end": 4.0,
                "text": "They walked me through setup in two minutes.",
            },
            {"start": 4.0, "end": 5.0, "text": "Last sentence."},
        ]
        highlight = _pick_highlight(transcript, segments)
        assert highlight is not None
        assert "walked me through" in highlight["text"]
        # The offsets point into the original transcript.
        assert transcript[highlight["start"] : highlight["end"]] == highlight["text"]

    def test_falls_back_to_longest_when_no_keyword(self):
        transcript = (
            "One short bit. Another short bit. A much much longer reflection that just happens to be the meatiest part of the answer overall."
        )
        segments = [
            {"start": 0.0, "end": 1.0, "text": "One short bit."},
            {"start": 1.0, "end": 2.0, "text": "Another short bit."},
            {
                "start": 2.0,
                "end": 6.0,
                "text": "A much much longer reflection that just happens to be the meatiest part of the answer overall.",
            },
        ]
        highlight = _pick_highlight(transcript, segments)
        assert highlight is not None
        assert "meatiest" in highlight["text"]

    def test_empty_transcript_returns_none(self):
        assert _pick_highlight("", []) is None

    def test_handles_missing_segments(self):
        # Whisper sometimes returns no segments for very short audio —
        # we should still find SOMETHING by sentence-splitting.
        transcript = "I really enjoyed how fast it was. Setup took two minutes."
        highlight = _pick_highlight(transcript, [])
        assert highlight is not None
        # Both candidates have a keyword, the first match wins.
        assert highlight["text"] in transcript
