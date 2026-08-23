"""House-style guard: no em/en dashes or double hyphens reach the user."""
from app.services.text_style import strip_banned_dashes, strip_banned_dashes_deep
from app.services import interview_engine


def test_between_words_becomes_comma():
    assert strip_banned_dashes("Short and clear — users skim.") == "Short and clear, users skim."
    assert strip_banned_dashes("court – clair") == "court, clair"
    assert strip_banned_dashes("one -- two") == "one, two"


def test_after_punctuation_is_dropped():
    assert strip_banned_dashes("Done. — Next step") == "Done. Next step"


def test_untouched_when_clean():
    text = "A follow-up question, with a hyphen."
    assert strip_banned_dashes(text) is text


def test_deep_sanitizes_nested_proposal_payload():
    actions = [
        {
            "type": "add_question",
            "question": {
                "prompt": "Why this — and not that?",
                "config": {"options": ["Price — too high", "Fine"]},
                "rationale": "Probe — gently.",
            },
        },
        {"type": "suggest_replies", "choices": ("Yes — go", "No")},
        {"type": "noop", "count": 3},
    ]
    out = strip_banned_dashes_deep(actions)
    assert out[0]["question"]["prompt"] == "Why this, and not that?"
    assert out[0]["question"]["config"]["options"] == ["Price, too high", "Fine"]
    assert out[0]["question"]["rationale"] == "Probe, gently."
    assert out[1]["choices"] == ("Yes, go", "No")
    assert out[2]["count"] == 3


def test_interview_engine_alias_still_wired():
    assert interview_engine._strip_banned_dashes("a — b") == "a, b"
