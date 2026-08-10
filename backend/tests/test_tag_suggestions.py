"""Tests for AI-suggested tags + starter codebook (services/tag_suggestions.py)."""

import json

from app.models.company import Company
from app.models.coding import ManualCode, QuoteTag, TagSuggestion
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.services.tag_suggestions import (
    suggest_starter_codes,
    suggest_tags_for_participant,
)

ANSWER_0 = "Honestly the checkout flow made me give up twice, I had to restart the whole payment."
ANSWER_1 = "I trust them because my colleagues use it daily and nothing ever broke."


def _graph(db_session, with_codes=True):
    company = Company(name="Tag Co", email="t@example.com", password_hash="x")
    db_session.add(company)
    db_session.commit()
    project = Project(
        company_id=company.id,
        name="Checkout study",
        language="en",
        research_objective="Understand payment friction",
        decision_to_inform="Rebuild checkout or iterate",
    )
    db_session.add(project)
    db_session.commit()
    link = InterviewLink(project_id=project.id, token="tok-tags-1")
    db_session.add(link)
    db_session.commit()
    p = Participant(link_id=link.id, project_id=project.id, display_name="Bo", status="completed")
    db_session.add(p)
    db_session.commit()
    turns = []
    for i, answer in enumerate([ANSWER_0, ANSWER_1]):
        t = InterviewTurn(
            participant_id=p.id, turn_index=i, question_index=i,
            question_text=f"Q{i}", response_transcript=answer,
        )
        db_session.add(t)
        turns.append(t)
    db_session.commit()
    codes = []
    if with_codes:
        for name in ["Friction", "Trust signal"]:
            c = ManualCode(project_id=project.id, name=name)
            db_session.add(c)
            codes.append(c)
        db_session.commit()
    return company, project, p, turns, codes


class _FakeMsg:
    def __init__(self, text):
        self.content = [type("B", (), {"text": text})()]
        self.usage = type(
            "U", (),
            {"input_tokens": 10, "output_tokens": 10,
             "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        )()


def _patch_client(monkeypatch, result: dict):
    def fake_create(**kwargs):
        return _FakeMsg(json.dumps(result))

    fake_client = type("C", (), {"messages": type("M", (), {"create": staticmethod(fake_create)})()})()
    monkeypatch.setattr("app.services._clients.get_anthropic_client", lambda *a, **k: fake_client)
    monkeypatch.setattr("app.services.usage_logger.log_claude_usage", lambda *a, **k: None)


class TestSuggestTags:
    def test_deductive_suggestion_resolves_offsets(self, db_session, monkeypatch):
        _, _, p, turns, codes = _graph(db_session)
        _patch_client(monkeypatch, {
            "suggestions": [
                {"code": "friction", "turn_index": 0, "quote": "made me give up twice"},
            ],
            "new_codes": [],
        })
        created = suggest_tags_for_participant(p.id, db_session, "en")
        assert len(created) == 1
        s = created[0]
        assert s.manual_code_id == codes[0].id  # case-insensitive match
        assert s.turn_id == turns[0].id
        assert ANSWER_0[s.start_index:s.end_index] == "made me give up twice"
        assert s.status == "pending"

    def test_paraphrase_and_unknown_code_dropped(self, db_session, monkeypatch):
        _, _, p, _, _ = _graph(db_session)
        _patch_client(monkeypatch, {
            "suggestions": [
                {"code": "Friction", "turn_index": 0, "quote": "he abandoned the checkout in frustration"},
                {"code": "Made-up code", "turn_index": 1, "quote": "nothing ever broke"},
            ],
            "new_codes": [],
        })
        assert suggest_tags_for_participant(p.id, db_session, "en") == []

    def test_wrong_turn_index_still_resolves(self, db_session, monkeypatch):
        _, _, p, turns, _ = _graph(db_session)
        _patch_client(monkeypatch, {
            "suggestions": [
                {"code": "Trust signal", "turn_index": 0, "quote": "my colleagues use it daily"},
            ],
            "new_codes": [],
        })
        created = suggest_tags_for_participant(p.id, db_session, "en")
        assert len(created) == 1
        assert created[0].turn_id == turns[1].id

    def test_new_code_cap_and_existing_name_filter(self, db_session, monkeypatch):
        _, _, p, _, _ = _graph(db_session)
        quote = {"turn_index": 0, "quote": "I had to restart the whole payment"}
        _patch_client(monkeypatch, {
            "suggestions": [],
            "new_codes": [
                {"name": "friction", "rationale": "dupe of existing", "quotes": [quote]},
                {"name": "Workaround", "rationale": "r1", "quotes": [quote]},
                {"name": "Reliability", "rationale": "r2",
                 "quotes": [{"turn_index": 1, "quote": "nothing ever broke"}]},
                {"name": "Over the cap", "rationale": "r3", "quotes": [quote]},
            ],
        })
        created = suggest_tags_for_participant(p.id, db_session, "en")
        names = {s.proposed_code_name for s in created}
        # existing-name dupe filtered before the cap, so both real codes
        # survive; the 4th proposal falls to the cap of 2
        assert names == {"Workaround", "Reliability"}

    def test_rerun_replaces_pending_keeps_reviewed(self, db_session, monkeypatch):
        _, _, p, _, _ = _graph(db_session)
        _patch_client(monkeypatch, {
            "suggestions": [{"code": "Friction", "turn_index": 0, "quote": "made me give up twice"}],
            "new_codes": [],
        })
        first = suggest_tags_for_participant(p.id, db_session, "en")
        first[0].status = "rejected"
        db_session.commit()
        second = suggest_tags_for_participant(p.id, db_session, "en")
        assert len(second) == 1
        all_rows = db_session.query(TagSuggestion).filter(
            TagSuggestion.participant_id == p.id
        ).all()
        assert len(all_rows) == 2  # rejected history + fresh pending

    def test_overlap_with_existing_tag_skipped(self, db_session, monkeypatch):
        _, _, p, turns, codes = _graph(db_session)
        start = ANSWER_0.find("made me give up twice")
        db_session.add(QuoteTag(
            turn_id=turns[0].id, manual_code_id=codes[0].id,
            selected_text="made me give up twice",
            start_index=start, end_index=start + len("made me give up twice"),
        ))
        db_session.commit()
        _patch_client(monkeypatch, {
            "suggestions": [{"code": "Friction", "turn_index": 0, "quote": "made me give up twice"}],
            "new_codes": [],
        })
        assert suggest_tags_for_participant(p.id, db_session, "en") == []

    def test_never_raises_on_model_garbage(self, db_session, monkeypatch):
        _, _, p, _, _ = _graph(db_session)
        fake_client = type("C", (), {"messages": type("M", (), {
            "create": staticmethod(lambda **kw: _FakeMsg("not json at all"))
        })()})()
        monkeypatch.setattr("app.services._clients.get_anthropic_client", lambda *a, **k: fake_client)
        monkeypatch.setattr("app.services.usage_logger.log_claude_usage", lambda *a, **k: None)
        assert suggest_tags_for_participant(p.id, db_session, "en") == []


class TestStarterCodes:
    def test_proposals_filtered_and_colored(self, db_session, monkeypatch):
        _, project, _, _, codes = _graph(db_session)
        _patch_client(monkeypatch, {
            "codes": [
                {"name": "Friction", "description": "dupe of existing, dropped"},
                {"name": "Workaround", "description": "user-built detours"},
                {"name": "workaround", "description": "case dupe, dropped"},
                {"name": "Price sensitivity", "description": "cost reactions"},
            ]
        })
        proposals = suggest_starter_codes(project, db_session, "en")
        assert [p["name"] for p in proposals] == ["Workaround", "Price sensitivity"]
        assert all(p["color"].startswith("#") for p in proposals)
        # nothing persisted
        assert db_session.query(ManualCode).filter(
            ManualCode.project_id == project.id
        ).count() == len(codes)

    def test_model_failure_returns_empty(self, db_session, monkeypatch):
        _, project, _, _, _ = _graph(db_session)
        fake_client = type("C", (), {"messages": type("M", (), {
            "create": staticmethod(lambda **kw: _FakeMsg("garbage"))
        })()})()
        monkeypatch.setattr("app.services._clients.get_anthropic_client", lambda *a, **k: fake_client)
        monkeypatch.setattr("app.services.usage_logger.log_claude_usage", lambda *a, **k: None)
        assert suggest_starter_codes(project, db_session, "en") == []
