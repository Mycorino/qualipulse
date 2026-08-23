"""Truncated-reply handling for the AI quality assessment.

A real interview lost its whole assessment in production because the reply
ran into the token cap mid-JSON and json.loads threw: the pass had already
been paid for, the rating and summary had already been generated, and all of
it was discarded. These tests cover the salvage, the retry, and the failure
stamp that lets the UI tell a crash from a run still in flight.
"""

import json

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.services.quality import _parse_assessment_json, run_ai_quality_assessment


def _graph(db_session, token="tok-trunc-1"):
    company = Company(name="Trunc Co", email=f"{token}@example.com", password_hash="x")
    db_session.add(company)
    db_session.commit()
    project = Project(company_id=company.id, name="Research practices", language="en")
    db_session.add(project)
    db_session.commit()
    link = InterviewLink(project_id=project.id, token=token)
    db_session.add(link)
    db_session.commit()
    p = Participant(
        link_id=link.id, project_id=project.id, display_name="Angelo", status="completed"
    )
    db_session.add(p)
    db_session.commit()
    db_session.add(
        InterviewTurn(
            participant_id=p.id,
            turn_index=0,
            question_index=0,
            question_text="How much user research do you do?",
            response_transcript=(
                "We ran about ten qualitative interviews per person at university, "
                "in groups of four, so thirty to forty people in total."
            ),
        )
    )
    db_session.commit()
    return p


class _FakeMsg:
    def __init__(self, text, stop_reason="max_tokens"):
        self.content = [type("B", (), {"text": text})()]
        self.stop_reason = stop_reason
        self.usage = type(
            "U",
            (),
            {
                "input_tokens": 4003,
                "output_tokens": 1024,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        )()


def _patch_client(monkeypatch, replies: list[str]):
    """Serve `replies` in order, one per messages.create call."""
    calls = {"n": 0}

    def fake_create(**kwargs):
        i = min(calls["n"], len(replies) - 1)
        calls["n"] += 1
        return _FakeMsg(replies[i])

    fake_client = type(
        "C", (), {"messages": type("M", (), {"create": staticmethod(fake_create)})()}
    )()
    monkeypatch.setattr(
        "app.services._clients.get_anthropic_client", lambda *a, **k: fake_client
    )
    monkeypatch.setattr(
        "app.services.usage_logger.log_claude_usage", lambda *a, **k: None
    )
    return calls


_FULL = {
    "quality_score": 0.62,
    "quality_label": "good",
    "summary": "Describes running roughly ten interviews in groups of four.",
    "strengths": ["Gave a concrete volume", "Named the group structure"],
    "issues": ["Vague on tooling"],
    "key_takeaways": ["Ran interviews in groups of four", "Thirty to forty people total"],
    "notable_quotes": ["in groups of four"],
}
_FULL_JSON = json.dumps(_FULL, ensure_ascii=False, indent=2)


class TestSalvage:
    """_parse_assessment_json recovers whatever arrived before the cut."""

    def test_intact_json_unchanged(self):
        assert _parse_assessment_json(_FULL_JSON) == _FULL

    def test_strips_fences_and_preamble(self):
        assert _parse_assessment_json("```json\n" + _FULL_JSON + "\n```") == _FULL
        assert _parse_assessment_json("Here you go:\n" + _FULL_JSON) == _FULL

    @pytest.mark.parametrize(
        "marker,offset",
        [
            ('"key_takeaways"', 60),   # cut inside a trailing list of strings
            ('"issues"', 40),          # cut inside a nested array
            ('"notable_quotes"', -2),  # cut exactly on a value boundary
        ],
    )
    def test_recovers_rating_from_truncated_reply(self, marker, offset):
        cut = _FULL_JSON[: _FULL_JSON.index(marker) + offset]
        with pytest.raises(json.JSONDecodeError):
            json.loads(cut)  # the shape that used to kill the whole pass
        result = _parse_assessment_json(cut)
        assert result["quality_label"] == "good"
        assert result["summary"] == _FULL["summary"]

    def test_rejects_salvage_that_lost_the_rating(self):
        # Cut before quality_label arrived: a half object is worse than a retry.
        cut = _FULL_JSON[: _FULL_JSON.index('"quality_label"')]
        with pytest.raises(ValueError):
            _parse_assessment_json(cut)

    def test_rejects_non_json(self):
        with pytest.raises(ValueError):
            _parse_assessment_json("I cannot assess this transcript.")


class TestAssessmentResilience:
    def test_truncated_reply_still_persists_the_assessment(self, db_session, monkeypatch):
        p = _graph(db_session, "tok-trunc-salvage")
        cut = _FULL_JSON[: _FULL_JSON.index('"key_takeaways"') + 60]
        calls = _patch_client(monkeypatch, [cut])
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert p.quality_summary == _FULL["summary"]
        assert p.quality_label == "good"
        assert p.quality_status == "ok"
        assert calls["n"] == 1, "salvage should not need a retry"

    def test_unusable_reply_retries_once_then_succeeds(self, db_session, monkeypatch):
        p = _graph(db_session, "tok-trunc-retry")
        calls = _patch_client(monkeypatch, ["not json at all", _FULL_JSON])
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert calls["n"] == 2
        assert p.quality_status == "ok"
        assert p.quality_summary == _FULL["summary"]

    def test_two_failures_stamp_the_participant_as_failed(self, db_session, monkeypatch):
        p = _graph(db_session, "tok-trunc-failed")
        calls = _patch_client(monkeypatch, ["not json", "still not json"])
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert calls["n"] == 2
        assert p.quality_status == "failed"
        assert not p.quality_summary
        # The heuristic label the API falls back to must not read as success.
        assert p.quality_score is None

    def test_failed_participant_can_be_reassessed(self, db_session, monkeypatch):
        p = _graph(db_session, "tok-trunc-recover")
        _patch_client(monkeypatch, ["not json", "not json"])
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert p.quality_status == "failed"

        _patch_client(monkeypatch, [_FULL_JSON])
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert p.quality_status == "ok"
        assert p.quality_summary == _FULL["summary"]
