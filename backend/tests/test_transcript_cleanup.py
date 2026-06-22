"""Tests for the ASR sense-check service (services/transcript_cleanup.py)."""

import json

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.services import transcript_cleanup


def _graph(db_session):
    company = Company(name="Air Co", email="c@example.com", password_hash="x")
    db_session.add(company)
    db_session.commit()
    project = Project(
        company_id=company.id,
        name="Air France long-haul experience",
        language="fr",
        research_objective="Understand long-haul flyer perceptions of Air France vs Lufthansa",
    )
    db_session.add(project)
    db_session.commit()
    link = InterviewLink(project_id=project.id, token="tok-clean-1")
    db_session.add(link)
    db_session.commit()
    p = Participant(link_id=link.id, project_id=project.id, display_name="Corino", status="completed")
    db_session.add(p)
    db_session.commit()
    return company, project, link, p


def _add_turn(db_session, p, idx, text, **kw):
    t = InterviewTurn(
        participant_id=p.id, turn_index=idx, question_index=idx,
        question_text=f"Q{idx}", response_transcript=text, **kw,
    )
    db_session.add(t)
    db_session.commit()
    return t


class _FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]
        self.usage = type("U", (), {"input_tokens": 10, "output_tokens": 10,
                                     "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})()


def _patch_client(monkeypatch, mapping):
    """Patch Anthropic + usage logger; the fake echoes corrections from `mapping`."""
    def fake_create(*, model, max_tokens, temperature, messages):
        payload = messages[0]["content"]
        items = json.loads(payload.split("<input>\n", 1)[1].split("\n</input>", 1)[0])
        out = [{"id": it["id"], "response": mapping.get(it["id"], it["response"])} for it in items]
        return _FakeMsg(json.dumps(out, ensure_ascii=False))

    fake_client = type("C", (), {"messages": type("M", (), {"create": staticmethod(fake_create)})()})()
    monkeypatch.setattr("app.services._clients.get_anthropic_client", lambda *a, **k: fake_client)
    monkeypatch.setattr("app.services.usage_logger.log_claude_usage", lambda *a, **k: None)


class TestTranscriptCleanup:
    def test_fixes_stored_separately_original_preserved(self, db_session, monkeypatch):
        _, _, _, p = _graph(db_session)
        t = _add_turn(db_session, p, 0, "j'ai volé avec la France de Rio à Paris")
        _patch_client(monkeypatch, {t.id: "j'ai volé avec Air France de Rio à Paris"})

        transcript_cleanup.cleanup_participant(p.id, db_session)
        db_session.refresh(t)

        assert t.response_transcript == "j'ai volé avec la France de Rio à Paris"  # untouched
        assert t.cleaned_response == "j'ai volé avec Air France de Rio à Paris"
        assert t.cleaned_at is not None

    def test_identical_correction_stamps_but_leaves_cleaned_null(self, db_session, monkeypatch):
        _, _, _, p = _graph(db_session)
        t = _add_turn(db_session, p, 0, "rien à corriger ici")
        _patch_client(monkeypatch, {})  # echoes input unchanged

        transcript_cleanup.cleanup_participant(p.id, db_session)
        db_session.refresh(t)

        assert t.cleaned_response is None       # no diff → no correction stored
        assert t.cleaned_at is not None         # but stamped so we don't re-run

    def test_idempotent_skips_already_cleaned(self, db_session, monkeypatch):
        _, _, _, p = _graph(db_session)
        t = _add_turn(db_session, p, 0, "la France c'était bien")
        calls = {"n": 0}
        orig = transcript_cleanup._cleanup_participant_inner

        _patch_client(monkeypatch, {t.id: "Air France c'était bien"})
        transcript_cleanup.cleanup_participant(p.id, db_session)
        db_session.refresh(t)
        first = t.cleaned_response

        # Second run: no pending turns → returns before any model call.
        def boom(*a, **k):
            calls["n"] += 1
            raise AssertionError("should not call the model again")
        monkeypatch.setattr("app.services._clients.get_anthropic_client", boom)
        transcript_cleanup.cleanup_participant(p.id, db_session)
        db_session.refresh(t)
        assert t.cleaned_response == first
        assert calls["n"] == 0

    def test_skips_manually_edited_turns(self, db_session, monkeypatch):
        _, _, _, p = _graph(db_session)
        t = _add_turn(db_session, p, 0, "researcher already fixed this", manually_edited=True)
        _patch_client(monkeypatch, {t.id: "SHOULD NOT APPLY"})

        transcript_cleanup.cleanup_participant(p.id, db_session)
        db_session.refresh(t)
        assert t.cleaned_response is None
        assert t.cleaned_at is None

    def test_never_raises_on_bad_model_output(self, db_session, monkeypatch):
        _, _, _, p = _graph(db_session)
        _add_turn(db_session, p, 0, "some text")
        fake_client = type("C", (), {"messages": type("M", (), {
            "create": staticmethod(lambda **k: _FakeMsg("not json at all"))})()})()
        monkeypatch.setattr("app.services._clients.get_anthropic_client", lambda *a, **k: fake_client)
        monkeypatch.setattr("app.services.usage_logger.log_claude_usage", lambda *a, **k: None)

        # Wrapper swallows the JSON error — must not raise.
        transcript_cleanup.cleanup_participant(p.id, db_session)
