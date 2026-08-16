"""Tests for the codebook evidence feed into project-level analysis."""

from app.models.company import Company
from app.models.coding import ManualCode, QuoteTag
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.services.analysis import _build_codebook_block, _codebook_stats


def _graph(db_session, n_participants=3):
    company = Company(name="CB Co", email="cb@example.com", password_hash="x")
    db_session.add(company)
    db_session.commit()
    project = Project(company_id=company.id, name="Codebook study", language="en")
    db_session.add(project)
    db_session.commit()
    link = InterviewLink(project_id=project.id, token="tok-cb-1")
    db_session.add(link)
    db_session.commit()
    participants, turns = [], []
    for i in range(n_participants):
        p = Participant(
            link_id=link.id, project_id=project.id,
            display_name=f"P{i}", status="completed",
        )
        db_session.add(p)
        db_session.commit()
        t = InterviewTurn(
            participant_id=p.id, turn_index=0, question_index=0,
            question_text="Q", response_transcript=f"answer text from participant {i}",
        )
        db_session.add(t)
        db_session.commit()
        participants.append(p)
        turns.append(t)
    return project, participants, turns


def _tag(db_session, turn, code, text="answer text"):
    tag = QuoteTag(
        turn_id=turn.id, manual_code_id=code.id,
        selected_text=text, start_index=0, end_index=len(text),
    )
    db_session.add(tag)
    db_session.commit()
    return tag


class TestCodebookStats:
    def test_counts_and_sorting(self, db_session):
        project, participants, turns = _graph(db_session)
        friction = ManualCode(project_id=project.id, name="Friction", color="#f00")
        trust = ManualCode(project_id=project.id, name="Trust", color="#0f0")
        db_session.add_all([friction, trust])
        db_session.commit()
        _tag(db_session, turns[0], friction)
        _tag(db_session, turns[1], friction)
        _tag(db_session, turns[1], friction, "second slice")
        _tag(db_session, turns[2], trust)

        stats = _codebook_stats(db_session, project.id, participants)
        assert [s["code"] for s in stats] == ["Friction", "Trust"]
        f = stats[0]
        assert f["tag_count"] == 3
        assert f["participant_count"] == 2
        assert f["participants_total"] == 3
        assert len(f["quotes"]) == 3

    def test_respects_participant_filter(self, db_session):
        project, participants, turns = _graph(db_session)
        code = ManualCode(project_id=project.id, name="Friction")
        db_session.add(code)
        db_session.commit()
        _tag(db_session, turns[0], code)
        _tag(db_session, turns[2], code)

        # Segment-filtered run only includes the first participant.
        stats = _codebook_stats(db_session, project.id, participants[:1])
        assert len(stats) == 1
        assert stats[0]["tag_count"] == 1
        assert stats[0]["participants_total"] == 1

    def test_empty_without_tags(self, db_session):
        project, participants, _ = _graph(db_session)
        db_session.add(ManualCode(project_id=project.id, name="Unused"))
        db_session.commit()
        assert _codebook_stats(db_session, project.id, participants) == []
        assert _build_codebook_block([]) == ""

    def test_block_renders_counts_and_quotes(self, db_session):
        project, participants, turns = _graph(db_session)
        code = ManualCode(project_id=project.id, name="Friction")
        db_session.add(code)
        db_session.commit()
        _tag(db_session, turns[0], code, "the checkout kept failing")

        stats = _codebook_stats(db_session, project.id, participants)
        block = _build_codebook_block(stats)
        assert "Friction: tagged in 1/3 interviews (1 quotes)" in block
        assert '"the checkout kept failing" (P0)' in block
        assert "RESEARCHER CODEBOOK EVIDENCE" in block
