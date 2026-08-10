"""Direct tests for the interview engine's turn logic.

Everything external (Whisper, Claude, TTS, storage) is monkeypatched at
the module boundary; what's under test is the orchestration itself:
transcript persistence, the close gate, the pace/follow-up server guards,
and completion side effects.
"""

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import InterviewGuideQuestion, Project
from app.services import interview_engine
from app.services.interview_engine import (
    EmptyTranscriptError,
    MAX_FOLLOWUPS_PER_QUESTION,
    process_interview_turn,
)

QUESTIONS = ["How do you work today?", "What tools do you use?", "What frustrates you?"]


def _seed(db, *, answered_up_to: int = 0, followups_on_current: int = 0):
    """Seed a 3-question interview.

    ``answered_up_to`` = number of main questions already fully answered;
    the participant is currently on question index ``answered_up_to`` with
    an unanswered interviewer turn waiting for their response.
    """
    company = Company(name="Acme", email="owner@acme.com", password_hash="x", email_verified=True)
    db.add(company)
    db.flush()
    project = Project(
        company_id=company.id, name="Study", language="en", interview_duration_minutes=20
    )
    db.add(project)
    db.flush()
    for i, q in enumerate(QUESTIONS):
        db.add(
            InterviewGuideQuestion(
                project_id=project.id,
                section_index=0,
                section_title="Main",
                question_index=i,
                main_question=q,
                sort_order=i,
            )
        )
    link = InterviewLink(project_id=project.id, token=f"tok-{answered_up_to}-{followups_on_current}", is_active=True)
    db.add(link)
    db.flush()
    participant = Participant(link_id=link.id, project_id=project.id, status="in_progress")
    db.add(participant)
    db.flush()

    turn_index = 0
    for i in range(answered_up_to):
        db.add(
            InterviewTurn(
                participant_id=participant.id,
                turn_index=turn_index,
                question_index=i,
                question_text=QUESTIONS[i],
                response_transcript=f"answer {i}",
            )
        )
        turn_index += 1
    current_q = answered_up_to
    for j in range(followups_on_current):
        db.add(
            InterviewTurn(
                participant_id=participant.id,
                turn_index=turn_index,
                question_index=current_q,
                is_follow_up=True,
                follow_up_index=j + 1,
                question_text=f"follow-up {j}",
                response_transcript=f"follow-up answer {j}",
            )
        )
        turn_index += 1
    # The pending interviewer turn awaiting the participant's answer.
    db.add(
        InterviewTurn(
            participant_id=participant.id,
            turn_index=turn_index,
            question_index=current_q,
            question_text=QUESTIONS[min(current_q, len(QUESTIONS) - 1)],
        )
    )
    db.commit()
    return participant


def _patch_io(monkeypatch, *, transcript="A long and thoughtful answer about my work.", decision=None):
    monkeypatch.setattr(interview_engine, "download_audio", lambda key: b"fake-bytes")
    monkeypatch.setattr(
        interview_engine,
        "transcribe_audio",
        lambda data, filename, language=None: (transcript, 12.0, []),
    )
    monkeypatch.setattr(interview_engine, "generate_speech", lambda text: b"fake-mp3")
    monkeypatch.setattr(interview_engine, "upload_audio", lambda data, key: f"/audio/{key}")
    if decision is not None:
        monkeypatch.setattr(
            interview_engine, "decide_next_action", lambda *a, **k: dict(decision)
        )


def test_follow_up_creates_follow_up_turn(db_session, monkeypatch):
    participant = _seed(db_session)
    _patch_io(
        monkeypatch,
        decision={"action": "follow_up", "question": "Tell me more about that?"},
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    assert turns[0].response_transcript == "A long and thoughtful answer about my work."
    new_turn = turns[-1]
    assert new_turn.is_follow_up is True
    assert new_turn.follow_up_index == 1
    assert new_turn.question_index == 0
    assert new_turn.question_text == "Tell me more about that?"


def test_next_question_advances_index(db_session, monkeypatch):
    participant = _seed(db_session)
    _patch_io(
        monkeypatch,
        decision={"action": "next_question", "question": "What tools do you use?"},
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.is_follow_up is False
    assert new_turn.question_index == 1


def test_premature_close_is_overridden(db_session, monkeypatch):
    """Claude says close on question 1 of 3 with <80% time used -> forced next_question."""
    participant = _seed(db_session)
    _patch_io(monkeypatch, decision={"action": "close", "question": "Thanks, goodbye!"})

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    db_session.refresh(participant)
    assert participant.status == "in_progress"
    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.question_index == 1


def test_close_when_all_questions_answered_completes(db_session, monkeypatch):
    participant = _seed(db_session, answered_up_to=2)  # on last question now
    _patch_io(monkeypatch, decision={"action": "close", "question": "Thanks, goodbye!"})

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is True
    db_session.refresh(participant)
    assert participant.status == "completed"
    assert participant.completed_at is not None


def test_follow_up_hard_cap_forces_advance(db_session, monkeypatch):
    participant = _seed(db_session, followups_on_current=MAX_FOLLOWUPS_PER_QUESTION)
    _patch_io(monkeypatch, decision={"action": "follow_up", "question": "One more thing?"})

    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.is_follow_up is False
    assert new_turn.question_index == 1


def test_empty_transcript_raises(db_session, monkeypatch):
    participant = _seed(db_session)
    _patch_io(monkeypatch, transcript="   ")

    with pytest.raises(EmptyTranscriptError):
        process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)


def test_whisper_hallucination_raises(db_session, monkeypatch):
    participant = _seed(db_session)
    _patch_io(monkeypatch, transcript="Thank you for watching!")

    with pytest.raises(EmptyTranscriptError):
        process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    # The phantom phrase must NOT be persisted as a real answer.
    pending = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert pending.response_transcript is None
