"""Tests for the interview digest riding on the AI quality assessment.

The completion-time Claude pass now also returns key_takeaways +
notable_quotes; these tests cover persistence, the verbatim-quote filter,
and the re-run guard.
"""

import json

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.services.quality import run_ai_quality_assessment


def _graph(db_session):
    company = Company(name="Digest Co", email="d@example.com", password_hash="x")
    db_session.add(company)
    db_session.commit()
    project = Project(company_id=company.id, name="Streaming habits", language="en")
    db_session.add(project)
    db_session.commit()
    link = InterviewLink(project_id=project.id, token="tok-digest-1")
    db_session.add(link)
    db_session.commit()
    p = Participant(
        link_id=link.id, project_id=project.id, display_name="Ana", status="completed"
    )
    db_session.add(p)
    db_session.commit()
    turn = InterviewTurn(
        participant_id=p.id,
        turn_index=0,
        question_index=0,
        question_text="How do you pick a streaming service?",
        response_transcript="I cancelled Netflix last month because the price went up twice in a year.",
    )
    db_session.add(turn)
    db_session.commit()
    return p


class _FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]
        self.usage = type(
            "U",
            (),
            {
                "input_tokens": 10,
                "output_tokens": 10,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            },
        )()


def _patch_client(monkeypatch, result: dict):
    def fake_create(**kwargs):
        return _FakeMsg(json.dumps(result))

    fake_client = type(
        "C", (), {"messages": type("M", (), {"create": staticmethod(fake_create)})()}
    )()
    monkeypatch.setattr(
        "app.services._clients.get_anthropic_client", lambda *a, **k: fake_client
    )
    monkeypatch.setattr(
        "app.services.usage_logger.log_claude_usage", lambda *a, **k: None
    )


_BASE_RESULT = {
    "quality_score": 0.8,
    "quality_label": "strong",
    "summary": "Concrete churn story with a price trigger.",
    "strengths": ["Named the exact cancellation trigger"],
    "issues": [],
}


class TestInterviewDigest:
    def test_persists_takeaways_and_verbatim_quotes(self, db_session, monkeypatch):
        p = _graph(db_session)
        _patch_client(
            monkeypatch,
            {
                **_BASE_RESULT,
                "key_takeaways": ["Cancelled Netflix over repeated price increases."],
                "notable_quotes": [
                    "the price went up twice in a year",  # verbatim substring
                    "I think prices are simply too high nowadays",  # paraphrase, must be dropped
                ],
            },
        )
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert json.loads(p.key_takeaways) == [
            "Cancelled Netflix over repeated price increases."
        ]
        assert json.loads(p.notable_quotes) == ["the price went up twice in a year"]

    def test_missing_digest_fields_persist_empty_lists(self, db_session, monkeypatch):
        p = _graph(db_session)
        _patch_client(monkeypatch, _BASE_RESULT)
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert json.loads(p.key_takeaways) == []
        assert json.loads(p.notable_quotes) == []
        # Quality fields still land as before.
        assert p.quality_label == "strong"
        assert p.quality_summary

    def test_rerun_guard_untouched(self, db_session, monkeypatch):
        p = _graph(db_session)
        p.quality_summary = "already assessed"
        db_session.commit()
        _patch_client(
            monkeypatch,
            {**_BASE_RESULT, "key_takeaways": ["SHOULD NOT APPLY"], "notable_quotes": []},
        )
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert p.key_takeaways is None
        assert p.quality_summary == "already assessed"

    def test_quote_filter_tolerates_wrapping_quotation_marks(self, db_session, monkeypatch):
        p = _graph(db_session)
        _patch_client(
            monkeypatch,
            {
                **_BASE_RESULT,
                "key_takeaways": [],
                "notable_quotes": ['"the price went up twice in a year"'],
            },
        )
        run_ai_quality_assessment(p.id, db_session, language="en")
        db_session.refresh(p)
        assert json.loads(p.notable_quotes) == ['"the price went up twice in a year"']
