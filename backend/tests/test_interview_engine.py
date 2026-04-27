"""Tests for the v2 interview engine.

Covers talk-time pacing, hard server-side caps, dead-air detection, fatigue
scoring, skip_to handling, and pre-flight planning.

The Anthropic and OpenAI clients are mocked at module entry-points so no
network calls are made.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import InterviewGuideQuestion, Project
from app.services import interview_engine as ie


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_project(db, n_questions: int = 3, total_minutes: int = 20) -> tuple[Company, Project, InterviewLink]:
    company = Company(name="T", email="t@test.com", password_hash="x")
    db.add(company)
    db.commit()
    db.refresh(company)

    project = Project(
        company_id=company.id,
        name="P",
        language="en",
        interview_duration_minutes=total_minutes,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    for i in range(n_questions):
        db.add(
            InterviewGuideQuestion(
                project_id=project.id,
                section_index=0,
                section_title="Sec",
                question_index=i,
                main_question=f"Question {i}",
                desired_learning="learn",
                sort_order=i,
            )
        )
    db.commit()

    link = InterviewLink(project_id=project.id, token="tok-test", is_active=True)
    db.add(link)
    db.commit()
    db.refresh(link)
    return company, project, link


def _make_participant(
    db,
    project: Project,
    link: InterviewLink,
    *,
    started_minutes_ago: float = 1.0,
    plan: dict | None = None,
) -> Participant:
    p = Participant(
        link_id=link.id,
        project_id=project.id,
        display_name="P",
        status="in_progress",
        started_at=datetime.utcnow() - timedelta(minutes=started_minutes_ago),
        interview_plan=json.dumps(plan) if plan else None,
        talk_seconds=0.0,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _add_turn(
    db,
    p: Participant,
    *,
    turn_index: int,
    question_index: int,
    question_text: str,
    response: str | None,
    turn_kind: str = "main",
    is_follow_up: bool = False,
) -> InterviewTurn:
    t = InterviewTurn(
        participant_id=p.id,
        turn_index=turn_index,
        question_index=question_index,
        question_text=question_text,
        response_transcript=response,
        is_follow_up=is_follow_up,
        follow_up_index=0,
        turn_kind=turn_kind,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def _claude_decision(payload: dict):
    """Build a fake Anthropic response object whose .content[0].text parses to payload."""
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    msg.model = "claude-sonnet-4-20250514"
    msg.stop_reason = "end_turn"
    return msg


def _wire_stream(client, *messages):
    """Wire a MagicMock anthropic client so that consecutive
    messages.stream(...) ctx-manager calls yield the supplied final messages.
    Each `messages` element can be a dict (auto-wrapped via _claude_decision)
    or a pre-built mock message object.
    """
    msgs = [_claude_decision(m) if isinstance(m, dict) else m for m in messages]

    def stream_factory(*args, **kwargs):
        ctx = MagicMock()
        if msgs:
            final = msgs.pop(0)
        else:
            final = _claude_decision({"action": "next_question", "question": "next"})
        ctx.__enter__.return_value.get_final_message.return_value = final
        ctx.__exit__.return_value = False
        return ctx

    client.messages.stream.side_effect = stream_factory
    return client


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestTalkTimeAndPlan:
    def test_talk_time_accumulates(self, db_session):
        """Participant.talk_seconds accumulates Whisper-reported durations."""
        _, project, link = _make_project(db_session)
        p = _make_participant(db_session, project, link)
        # Seed an "interviewer-asked" turn awaiting a response.
        _add_turn(
            db_session, p, turn_index=0, question_index=0,
            question_text="Q0", response=None, turn_kind="main",
        )
        # Mock STT to return varying durations.
        durations = [5.0, 8.0, 12.0]
        decisions = [
            {"action": "next_question", "question": "Q1"},
            {"action": "next_question", "question": "Q2"},
            {"action": "close", "question": "bye"},
        ]
        with patch("app.services.interview_engine.transcribe_audio") as stt, \
             patch("app.services.interview_engine.download_audio", return_value=b""), \
             patch("app.services.interview_engine.anthropic.Anthropic") as anth:
            stt.side_effect = [(f"answer with eight words here right now ok", d) for d in durations]
            client = MagicMock()
            _wire_stream(client, *decisions)
            anth.return_value = client

            for _ in range(3):
                ie.process_interview_turn(p.id, "fake/path.webm", db_session)

        db_session.refresh(p)
        assert p.talk_seconds == pytest.approx(25.0, abs=0.01)

    def test_interview_plan_generated_at_start(self, db_session):
        """start_interview should populate participant.interview_plan."""
        _, project, link = _make_project(db_session)
        p = _make_participant(db_session, project, link)
        # No ANTHROPIC_API_KEY set in test env → falls back to uniform plan.
        ie.start_interview(p.id, db_session)
        db_session.refresh(p)
        assert p.interview_plan is not None
        plan = json.loads(p.interview_plan)
        assert isinstance(plan, dict)
        assert "questions" in plan
        assert len(plan["questions"]) == 3
        assert all("budget_minutes" in q for q in plan["questions"])
        assert all("max_follow_ups" in q for q in plan["questions"])

    def test_legacy_participant_without_plan_still_works(self, db_session):
        """A participant whose interview_plan is null must still get a decision."""
        _, project, link = _make_project(db_session)
        p = _make_participant(db_session, project, link, plan=None)
        _add_turn(
            db_session, p, turn_index=0, question_index=0,
            question_text="Q0", response=None,
        )

        with patch("app.services.interview_engine.transcribe_audio", return_value=("nice answer with several words here", 6.0)), \
             patch("app.services.interview_engine.download_audio", return_value=b""), \
             patch("app.services.interview_engine.anthropic.Anthropic") as anth:
            client = MagicMock()
            _wire_stream(client, {"action": "next_question", "question": "Q1"})
            anth.return_value = client

            result = ie.process_interview_turn(p.id, "fake/path.webm", db_session)

        assert result["is_complete"] is False
        assert result["question_text"] == "Q1"


class TestHardCaps:
    def test_hard_cap_follow_ups_overrides_model(self, db_session):
        """Two follow-ups already exist → model's follow_up is overridden to next_question."""
        plan = {
            "questions": [
                {"index": 0, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 1, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 2, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
            ],
            "total_budget_minutes": 20,
        }
        _, project, link = _make_project(db_session)
        p = _make_participant(db_session, project, link, plan=plan)
        # Main turn + 2 follow-up turns on Q0, then a fresh interviewer turn awaiting answer
        _add_turn(db_session, p, turn_index=0, question_index=0, question_text="Q0",
                  response="answer one with several words", turn_kind="main")
        _add_turn(db_session, p, turn_index=1, question_index=0, question_text="FU1",
                  response="follow up answer one ok", turn_kind="follow_up", is_follow_up=True)
        _add_turn(db_session, p, turn_index=2, question_index=0, question_text="FU2",
                  response="follow up answer two ok", turn_kind="follow_up", is_follow_up=True)
        _add_turn(db_session, p, turn_index=3, question_index=0, question_text="FU3?",
                  response=None, turn_kind="follow_up", is_follow_up=True)

        with patch("app.services.interview_engine.transcribe_audio", return_value=("third answer right here", 6.0)), \
             patch("app.services.interview_engine.download_audio", return_value=b""), \
             patch("app.services.interview_engine.anthropic.Anthropic") as anth:
            client = MagicMock()
            # Model wants ANOTHER follow_up — server must override to next_question
            _wire_stream(client, {"action": "follow_up", "question": "yet another follow up?"})
            anth.return_value = client

            result = ie.process_interview_turn(p.id, "f.webm", db_session)

        # Inspect the newly-saved turn — it should be a "main" Q1 ask, not a follow_up.
        last = db_session.query(InterviewTurn).filter(InterviewTurn.participant_id == p.id) \
            .order_by(InterviewTurn.turn_index.desc()).first()
        assert last.turn_kind == "main"
        assert last.is_follow_up is False
        assert last.question_index == 1

    def test_skip_to_creates_synthetic_skip_turns(self, db_session):
        plan = {
            "questions": [
                {"index": 0, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "deep"},
                {"index": 1, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 2, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
            ],
            "total_budget_minutes": 20,
        }
        _, project, link = _make_project(db_session, n_questions=3)
        p = _make_participant(db_session, project, link, plan=plan)
        _add_turn(db_session, p, turn_index=0, question_index=0, question_text="Q0",
                  response=None, turn_kind="main")

        with patch("app.services.interview_engine.transcribe_audio", return_value=(
                "I already use Tool X and it covers what you'd ask in Q1 too", 9.0)), \
             patch("app.services.interview_engine.download_audio", return_value=b""), \
             patch("app.services.interview_engine.anthropic.Anthropic") as anth:
            client = MagicMock()
            _wire_stream(client, {
                "action": "skip_to",
                "question": "On Q2 — walk me through that",
                "skip_to_question_index": 2,
            })
            anth.return_value = client

            ie.process_interview_turn(p.id, "f.webm", db_session)

        turns = sorted(p.turns, key=lambda t: t.turn_index)
        # Should contain: main Q0 (now answered), skip_skip for Q1, main ask for Q2
        kinds = [(t.question_index, t.turn_kind) for t in turns]
        assert (1, "skip_skip") in kinds
        assert (2, "main") in kinds
        # The skip_skip row should have the synthetic transcript filled in.
        skip_row = next(t for t in turns if t.turn_kind == "skip_skip")
        assert "Implicitly answered" in (skip_row.response_transcript or "")

    def test_clarification_max_is_one_per_question(self, db_session):
        """A second dead-air on the same question is forced to next_question."""
        plan = {
            "questions": [
                {"index": 0, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 1, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 2, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
            ],
            "total_budget_minutes": 20,
        }
        _, project, link = _make_project(db_session)
        p = _make_participant(db_session, project, link, plan=plan)
        _add_turn(db_session, p, turn_index=0, question_index=0, question_text="Q0",
                  response="real first answer here you go", turn_kind="main")
        _add_turn(db_session, p, turn_index=1, question_index=0,
                  question_text="clarification re-prompt", response="yeah",
                  turn_kind="clarification")
        _add_turn(db_session, p, turn_index=2, question_index=0,
                  question_text="next ask awaiting answer", response=None,
                  turn_kind="follow_up", is_follow_up=True)

        with patch("app.services.interview_engine.transcribe_audio", return_value=("yeah", 1.5)), \
             patch("app.services.interview_engine.download_audio", return_value=b""), \
             patch("app.services.interview_engine.anthropic.Anthropic") as anth:
            client = MagicMock()
            _wire_stream(client, {"action": "next_question", "question": "Q1"})
            anth.return_value = client

            ie.process_interview_turn(p.id, "f.webm", db_session)

        last = db_session.query(InterviewTurn).filter(InterviewTurn.participant_id == p.id) \
            .order_by(InterviewTurn.turn_index.desc()).first()
        # Second dead-air should NOT save another clarification — it should advance.
        assert last.turn_kind != "clarification"
        assert last.question_index == 1


class TestDeadAir:
    def test_dead_air_triggers_clarification_without_calling_claude(self, db_session):
        """A 'yeah' answer of <3s should reprompt without invoking Claude."""
        _, project, link = _make_project(db_session)
        p = _make_participant(db_session, project, link)
        _add_turn(db_session, p, turn_index=0, question_index=0, question_text="Q0",
                  response=None, turn_kind="main")

        anth_mock = MagicMock()
        with patch("app.services.interview_engine.transcribe_audio", return_value=("Yeah.", 1.5)), \
             patch("app.services.interview_engine.download_audio", return_value=b""), \
             patch("app.services.interview_engine.anthropic.Anthropic", anth_mock):
            ie.process_interview_turn(p.id, "f.webm", db_session)

        # Anthropic.Anthropic shouldn't have been instantiated for the dead-air path.
        anth_mock.assert_not_called()

        last = db_session.query(InterviewTurn).filter(InterviewTurn.participant_id == p.id) \
            .order_by(InterviewTurn.turn_index.desc()).first()
        assert last.turn_kind == "clarification"
        assert last.question_index == 0


class TestFatigue:
    def test_fatigue_high_opens_close_gate_early(self, db_session):
        """6 turns where late words ≪ early words → fatigue=high → close gate at 70/70."""
        plan = {
            "questions": [
                {"index": 0, "budget_minutes": 3.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 1, "budget_minutes": 3.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 2, "budget_minutes": 3.0, "max_follow_ups": 2, "depth": "standard"},
            ],
            "total_budget_minutes": 10,
        }
        _, project, link = _make_project(db_session, total_minutes=10)
        p = _make_participant(db_session, project, link, plan=plan)
        long_answer = " ".join(["word"] * 80)
        short_answer = " ".join(["w"] * 5)
        # 6 answer turns: first 2 long (≈80 words avg), last 2 short (≈5 words avg)
        # ratio ≈ 5/80 = 0.06 → high
        _add_turn(db_session, p, turn_index=0, question_index=0, question_text="Q0",
                  response=long_answer, turn_kind="main")
        _add_turn(db_session, p, turn_index=1, question_index=0, question_text="Q0fu",
                  response=long_answer, turn_kind="follow_up", is_follow_up=True)
        _add_turn(db_session, p, turn_index=2, question_index=1, question_text="Q1",
                  response="medium answer with a few words here ok", turn_kind="main")
        _add_turn(db_session, p, turn_index=3, question_index=1, question_text="Q1fu",
                  response="another medium response there ok", turn_kind="follow_up",
                  is_follow_up=True)
        _add_turn(db_session, p, turn_index=4, question_index=2, question_text="Q2",
                  response=short_answer, turn_kind="main")
        _add_turn(db_session, p, turn_index=5, question_index=2, question_text="Q2fu",
                  response=short_answer, turn_kind="follow_up", is_follow_up=True)

        turns = sorted(p.turns, key=lambda t: t.turn_index)
        fatigue = ie._compute_fatigue_state(turns)
        assert fatigue == "high"

        # Now exercise the close gate via decide_next_action. With talk_minutes=7
        # (70%) and questions answered = 3/3 → all_questions_done True, fatigue
        # high → gate should be open. We just assert the helper logic produces
        # a "close-allowed" prompt.
        with patch("app.services.interview_engine.anthropic.Anthropic") as anth:
            client = MagicMock()
            _wire_stream(client, {"action": "close", "question": "wrap"})
            anth.return_value = client
            decision = ie.decide_next_action(
                system_prompt="",
                interview_guide_str="<g>",
                conversation_history="",
                current_question_index=2,
                elapsed_minutes=8.0,
                total_minutes=10,
                all_questions_done=True,
                total_questions=3,
                talk_minutes=7.1,
                interview_plan=plan,
                fatigue_state="high",
                turns=turns,
            )
        # The model was allowed to close — verify the user message contained
        # the open close gate.
        sent = client.messages.stream.call_args.kwargs["messages"][0]["content"]
        assert "Close gate: OPEN" in sent
        assert decision["action"] == "close"


class TestPacingOverrides:
    def test_pacing_uses_talk_time_not_wall_clock(self, db_session):
        """5 wall-clock min, 2 talk min → pacing overall_pct ≈ 20% (ahead)."""
        plan = {
            "questions": [
                {"index": 0, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 1, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
            ],
            "total_budget_minutes": 10,
        }
        # 5 min wall clock, 2 min talk
        pacing = ie._compute_pacing(
            plan=plan,
            turns=[],
            current_question_index=0,
            talk_minutes=2.0,
            elapsed_minutes=5.0,
            total_minutes=10,
            total_questions=2,
        )
        assert pacing["overall_pct"] == pytest.approx(20.0)
        # talk-time is ahead — overall_pace shouldn't be "behind"
        assert pacing["overall_pace"] != "behind"
        assert pacing["wall_clock_overshoot"] is False

    def test_wall_clock_overshoot_forces_close(self, db_session):
        """elapsed > 1.5x total → server forces close even when model said next_question."""
        plan = {
            "questions": [
                {"index": 0, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
                {"index": 1, "budget_minutes": 5.0, "max_follow_ups": 2, "depth": "standard"},
            ],
            "total_budget_minutes": 10,
        }
        _, project, link = _make_project(db_session, n_questions=2, total_minutes=10)
        # started 25 min ago → 250% of total
        p = _make_participant(db_session, project, link, started_minutes_ago=25.0, plan=plan)
        _add_turn(db_session, p, turn_index=0, question_index=0, question_text="Q0",
                  response=None, turn_kind="main")

        with patch("app.services.interview_engine.transcribe_audio", return_value=("answer here ok", 4.0)), \
             patch("app.services.interview_engine.download_audio", return_value=b""), \
             patch("app.services.interview_engine.anthropic.Anthropic") as anth:
            client = MagicMock()
            _wire_stream(client, {"action": "next_question", "question": "Q1"})
            anth.return_value = client

            result = ie.process_interview_turn(p.id, "f.webm", db_session)

        assert result["is_complete"] is True
        last = db_session.query(InterviewTurn).filter(InterviewTurn.participant_id == p.id) \
            .order_by(InterviewTurn.turn_index.desc()).first()
        assert last.turn_kind == "closing"
