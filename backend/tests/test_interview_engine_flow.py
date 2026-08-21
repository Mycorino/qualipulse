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
        lambda data, filename, language=None, prompt=None: (transcript, 12.0, []),
    )
    monkeypatch.setattr(
        interview_engine, "generate_speech", lambda text, language=None: b"fake-mp3"
    )
    monkeypatch.setattr(
        interview_engine, "_spawn_completion_side_effects", lambda pid: None
    )
    monkeypatch.setattr(interview_engine, "upload_audio", lambda data, key: f"/audio/{key}")
    if decision is not None:
        calls: list[dict] = []

        def _decide(*a, **k):
            calls.append(k)
            forced = k.get("forced_action")
            if forced:
                return {
                    "action": forced,
                    "question": f"[regenerated for {forced}]",
                    "coaching": None,
                }
            return dict(decision)

        monkeypatch.setattr(interview_engine, "decide_next_action", _decide)
        return calls
    return None


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


def test_close_asks_the_final_check_first(db_session, monkeypatch):
    """The first "close" becomes the "anything we haven't covered?" turn."""
    participant = _seed(db_session, answered_up_to=2)  # on last question now
    _patch_io(monkeypatch, decision={"action": "close", "question": "Thanks, goodbye!"})

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    assert result["question_index"] == interview_engine.FINAL_CHECK_QUESTION_INDEX
    db_session.refresh(participant)
    assert participant.status == "in_progress"


def test_close_after_final_check_completes(db_session, monkeypatch):
    participant = _seed(db_session, answered_up_to=2)
    _patch_io(monkeypatch, decision={"action": "close", "question": "Thanks, goodbye!"})

    # Turn 1: the closing check is asked and answered.
    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)
    # Turn 2: the model closes for real.
    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is True
    db_session.refresh(participant)
    assert participant.status == "completed"
    assert participant.completed_at is not None
    assert participant.completion_reason == "natural"


def test_end_early_completes_and_flags_reason(db_session, monkeypatch):
    """A participant asking to stop is honoured immediately."""
    participant = _seed(db_session, answered_up_to=2)
    _patch_io(
        monkeypatch,
        transcript="Sorry, I have to go now, can we stop here?",
        decision={
            "action": "end_early",
            "question": "Of course, thank you for your time.",
            "stop_quote": "I have to go now, can we stop here",
        },
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is True
    db_session.refresh(participant)
    assert participant.status == "completed"
    assert participant.completion_reason == "participant_requested"


def test_end_early_on_first_question_is_not_billed(db_session, monkeypatch):
    """Stopping after one answer of three is not a usable interview."""
    consumed = []
    import app.services.billing_service as billing

    monkeypatch.setattr(
        billing, "consume_interview_credit",
        lambda *a, **k: consumed.append(k) or None,
    )
    participant = _seed(db_session)  # on question 0 of 3
    _patch_io(
        monkeypatch,
        transcript="I need to stop the interview here, sorry.",
        decision={
            "action": "end_early",
            "question": "No problem, take care.",
            "stop_quote": "I need to stop the interview here",
        },
    )

    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    db_session.refresh(participant)
    assert participant.status == "completed"
    assert consumed == []


def test_pace_guard_regenerates_wording_for_forced_action(db_session, monkeypatch):
    """A forced next_question must not speak the follow-up Claude wrote."""
    from datetime import datetime, timedelta

    # Three turns all on question 0, four minutes apart: 12 active minutes
    # of a 20-minute budget spent without leaving the first topic.
    participant = _seed(db_session, followups_on_current=2)
    now = datetime.utcnow()
    participant.started_at = now - timedelta(minutes=12)
    for i, turn in enumerate(sorted(participant.turns, key=lambda t: t.turn_index)):
        turn.created_at = now - timedelta(minutes=12 - 4 * i)
    db_session.commit()
    calls = _patch_io(
        monkeypatch,
        decision={"action": "follow_up", "question": "Tell me more about that?"},
    )

    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.question_index == 1
    assert new_turn.is_follow_up is False
    # The spoken text is the regenerated one, never the stale follow-up.
    assert new_turn.question_text == "[regenerated for next_question]"
    assert any(c.get("forced_action") == "next_question" for c in calls)


def test_follow_up_cap_regenerates_wording(db_session, monkeypatch):
    participant = _seed(db_session, followups_on_current=MAX_FOLLOWUPS_PER_QUESTION)
    calls = _patch_io(
        monkeypatch, decision={"action": "follow_up", "question": "One more thing?"}
    )

    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.question_text == "[regenerated for next_question]"
    assert any(c.get("forced_action") == "next_question" for c in calls)


def test_ai_outage_falls_back_to_next_guide_question(db_session, monkeypatch):
    """Claude down mid-interview must not 500 the participant."""
    participant = _seed(db_session)
    _patch_io(monkeypatch)

    def _boom(*a, **k):
        raise interview_engine.InterviewAIUnavailable("down")

    monkeypatch.setattr(interview_engine, "decide_next_action", _boom)
    monkeypatch.setattr(interview_engine, "_spawn_completion_side_effects", lambda pid: None)

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.question_index == 1
    assert QUESTIONS[1] in new_turn.question_text


def test_finish_interview_is_idempotent(db_session, monkeypatch):
    participant = _seed(db_session, answered_up_to=2)
    _patch_io(monkeypatch)
    monkeypatch.setattr(interview_engine, "_cached_tts", lambda text, language=None: None)

    first = interview_engine.finish_interview(participant.id, db_session)
    second = interview_engine.finish_interview(participant.id, db_session)

    assert first["is_complete"] is True
    assert second["turn_index"] == first["turn_index"]
    db_session.refresh(participant)
    assert participant.completion_reason == "participant_finished"
    assert len([t for t in participant.turns if t.question_text == first["question_text"]]) == 1


def test_long_answer_containing_hallucination_phrase_is_kept(db_session, monkeypatch):
    """The guard must only fire on short clips, not on real answers."""
    participant = _seed(db_session)
    _patch_io(
        monkeypatch,
        transcript=(
            "I watch a lot of tutorials for this, and honestly at the end they all say "
            "thanks for watching, which is when I go back to the dashboard and try it myself."
        ),
        decision={"action": "follow_up", "question": "What happened next?"},
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    assert "thanks for watching" in result["transcript"].lower()


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


# ── pacing clock ────────────────────────────────────────────────────────────

def test_a_long_break_does_not_consume_the_time_budget(db_session):
    """Pausing, taking a call, or locking the phone must not rush the rest
    of the interview."""
    from datetime import datetime, timedelta

    participant = _seed(db_session, answered_up_to=1)
    now = datetime.utcnow()
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    # Q1 asked at T+0 and answered promptly; then a 45-minute break; the
    # current question was asked one minute ago.
    turns[0].created_at = now - timedelta(minutes=48)
    turns[1].created_at = now - timedelta(minutes=1)
    participant.started_at = now - timedelta(minutes=48)
    db_session.commit()

    ctx = interview_engine.get_interview_context(participant.id, db_session)

    # Raw wall clock would be 48 minutes (way past the 20-minute budget).
    # Active time is ~2 x the 5-minute cap plus the open minute.
    assert ctx["elapsed_minutes"] < 12
    assert ctx["elapsed_minutes"] > 5


def test_steady_thinking_time_still_counts_in_full(db_session):
    """A slow, considered participant is not given free extra time."""
    from datetime import datetime, timedelta

    participant = _seed(db_session, answered_up_to=1)
    now = datetime.utcnow()
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    turns[0].created_at = now - timedelta(minutes=8)
    turns[1].created_at = now - timedelta(minutes=4)
    participant.started_at = now - timedelta(minutes=8)
    db_session.commit()

    ctx = interview_engine.get_interview_context(participant.id, db_session)

    # Two 4-minute stretches, both under the cap: all 8 minutes count.
    assert 7.5 < ctx["elapsed_minutes"] < 8.5


def test_warmup_time_does_not_count_against_the_budget(db_session):
    """The icebreaker must not make a short interview start 'behind'."""
    from datetime import datetime, timedelta

    from app.models.interview import InterviewTurn as _Turn

    participant = _seed(db_session)
    now = datetime.utcnow()
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    # Rewrite turn 0 as a warm-up asked 3 minutes ago and answered, with the
    # first guide question asked one minute ago.
    turns[0].question_index = interview_engine.WARMUP_QUESTION_INDEX
    turns[0].question_text = "How has your week been?"
    turns[0].response_transcript = "Busy but good."
    turns[0].created_at = now - timedelta(minutes=3)
    db_session.add(
        _Turn(
            participant_id=participant.id, turn_index=1, question_index=0,
            question_text=QUESTIONS[0], created_at=now - timedelta(minutes=1),
        )
    )
    participant.started_at = now - timedelta(minutes=3)
    db_session.commit()

    ctx = interview_engine.get_interview_context(participant.id, db_session)

    # Only the minute since the first real question counts, not the warm-up.
    assert ctx["elapsed_minutes"] < 1.5


# ── system prompt layering ──────────────────────────────────────────────────

def test_default_boilerplate_never_replaces_the_methodology():
    """Every project ships DEFAULT_SYSTEM_PROMPT; it must not drop the
    engine's decision rules, which is what `system_prompt or ...` did."""
    from app.models.project import DEFAULT_SYSTEM_PROMPT

    built = interview_engine._effective_system_prompt(DEFAULT_SYSTEM_PROMPT, "en")

    assert "follow_up" in built and "end_early" in built
    assert "Probing toolkit" in built
    # Untouched boilerplate is dropped rather than sent as noise.
    assert "never reveal the full interview guide" not in built.lower()


def test_custom_study_prompt_is_layered_on_top_not_substituted():
    built = interview_engine._effective_system_prompt(
        "Focus on pricing objections. Use the participant's industry jargon.", "en"
    )

    assert "Focus on pricing objections." in built
    assert "<researcher_instructions>" in built
    # The operational contract survives alongside it.
    assert "end_early" in built
    assert "never override the decision rules" in built


def test_blank_study_prompt_falls_back_to_methodology():
    assert "follow_up" in interview_engine._effective_system_prompt(None, "en")
    assert "follow_up" in interview_engine._effective_system_prompt("   ", "en")


def test_language_instruction_still_appended():
    built = interview_engine._effective_system_prompt(None, "fr")
    assert "French" in built


def test_end_early_needs_a_quote_from_the_participant(db_session, monkeypatch):
    """A stop the participant never asked for must not end the session."""
    participant = _seed(db_session, answered_up_to=1)
    _patch_io(
        monkeypatch,
        transcript="Yeah I'm done with that topic, it works fine for me.",
        decision={
            "action": "end_early",
            "question": "Thanks so much, take care!",
            "stop_quote": "I want to stop the interview",  # never said
        },
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    db_session.refresh(participant)
    assert participant.status == "in_progress"


def test_end_early_without_any_quote_is_rejected(db_session, monkeypatch):
    participant = _seed(db_session, answered_up_to=1)
    _patch_io(
        monkeypatch,
        transcript="It is mostly fine, we use it every Monday.",
        decision={"action": "end_early", "question": "Thanks, goodbye!"},
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    db_session.refresh(participant)
    assert participant.status == "in_progress"


def test_stop_request_grounding_helper():
    g = interview_engine._stop_request_is_grounded
    assert g("can we stop here", "Sorry, can we stop here? I have a call.")
    # Punctuation and case differences still match.
    assert g("I have to go now", "i have to GO now!!")
    assert not g("I want to stop", "This tool is fine, I have no complaints.")
    assert not g(None, "anything")
    assert not g("", "anything")
    assert not g("stop", None)


def test_skip_to_end_without_real_answers_is_not_billed(db_session, monkeypatch):
    """A transcript that is entirely [Skipped] is not a usable interview."""
    consumed = []
    monkeypatch.setattr(
        interview_engine, "_consume_credit_isolated",
        lambda billing: consumed.append(billing) if billing else None,
    )
    monkeypatch.setattr(interview_engine, "_cached_tts", lambda text, language=None: None)
    monkeypatch.setattr(interview_engine, "_spawn_completion_side_effects", lambda pid: None)

    participant = _seed(db_session, answered_up_to=2)
    for turn in participant.turns:
        turn.response_transcript = "[Skipped]"
    db_session.commit()

    interview_engine.skip_question(participant.id, db_session)

    db_session.refresh(participant)
    assert participant.status == "completed"
    assert consumed == []
