"""Direct tests for the interview engine's turn logic.

Everything external (Whisper, Claude, TTS, storage) is monkeypatched at
the module boundary; what's under test is the orchestration itself:
transcript persistence, the close gate, the pace/follow-up server guards,
and completion side effects.
"""

import uuid

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import InterviewGuideQuestion, Project
from app.services import interview_engine
from app.services.interview_engine import (
    AHEAD_PACE_QUESTIONS,
    EmptyTranscriptError,
    GUIDE_COVERED_CLOSE_FLOOR_PCT,
    MAX_FOLLOWUPS_CEILING,
    MAX_FOLLOWUPS_PER_QUESTION,
    _close_gate_open,
    _followup_allowance,
    process_interview_turn,
)

QUESTIONS = ["How do you work today?", "What tools do you use?", "What frustrates you?"]

# The seeded study is 20 minutes over 3 questions; the follow-up cap is derived
# from that budget rather than being a flat constant.
SEEDED_ALLOWANCE = _followup_allowance(20, len(QUESTIONS))

# The shape of the interview this regression came from: a 60-minute study over
# 7 guide questions, which reached its last question at minute 20.
BIG = dict(question_count=7, duration_minutes=60)
BIG_ALLOWANCE = _followup_allowance(60, 7)


def _seed(
    db,
    *,
    answered_up_to: int = 0,
    followups_on_current: int = 0,
    question_count: int | None = None,
    duration_minutes: int = 20,
):
    """Seed a 3-question interview (or a larger one via ``question_count``).

    ``answered_up_to`` = number of main questions already fully answered;
    the participant is currently on question index ``answered_up_to`` with
    an unanswered interviewer turn waiting for their response.
    """
    questions = list(QUESTIONS)
    while question_count is not None and len(questions) < question_count:
        questions.append(f"Extra guide question {len(questions)}?")
    if question_count is not None:
        questions = questions[:question_count]

    company = Company(
        name="Acme", email=f"owner-{uuid.uuid4().hex[:8]}@acme.com", password_hash="x", email_verified=True
    )
    db.add(company)
    db.flush()
    project = Project(
        company_id=company.id,
        name="Study",
        language="en",
        interview_duration_minutes=duration_minutes,
    )
    db.add(project)
    db.flush()
    for i, q in enumerate(questions):
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
    link = InterviewLink(project_id=project.id, token=f"tok-{uuid.uuid4().hex[:12]}", is_active=True)
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
                question_text=questions[i],
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
            question_text=questions[min(current_q, len(questions) - 1)],
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
    participant = _seed(db_session, followups_on_current=SEEDED_ALLOWANCE)
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


@pytest.mark.parametrize("transcript", ["...", "… … … … …", ". . .", "-", "…"])
def test_punctuation_only_transcript_raises(db_session, monkeypatch, transcript):
    """Whisper renders muted-mic clips as dots-only filler, not empty strings.

    Regression: a participant with a dead mic got '...' saved as an answer
    on every turn and the interviewer rolled through the whole guide.
    """
    participant = _seed(db_session)
    _patch_io(monkeypatch, transcript=transcript)

    with pytest.raises(EmptyTranscriptError):
        process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    pending = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert pending.response_transcript is None


def _patch_io_with_segments(monkeypatch, transcript, segments, decision=None):
    _patch_io(monkeypatch, transcript=transcript, decision=decision)
    monkeypatch.setattr(
        interview_engine,
        "transcribe_audio",
        lambda data, filename, language=None, prompt=None: (transcript, 12.0, segments),
    )


def test_all_segments_no_speech_raises(db_session, monkeypatch):
    """Whisper's own no_speech_prob catches hallucinations the phrase list misses."""
    participant = _seed(db_session)
    _patch_io_with_segments(
        monkeypatch,
        "Sottotitoli a cura di QTSS",  # novel hallucination, not in the phrase list
        [{"start": 0.0, "end": 4.0, "text": "Sottotitoli a cura di QTSS", "no_speech_prob": 0.97}],
    )

    with pytest.raises(EmptyTranscriptError):
        process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)


def test_long_answer_with_high_no_speech_prob_is_kept(db_session, monkeypatch):
    """The no_speech guard only applies to short clips: a real answer survives."""
    participant = _seed(db_session)
    long_answer = (
        "Well I usually start my day by going through the reservations that came in "
        "overnight and checking which rooms need attention before the morning rush."
    )
    _patch_io_with_segments(
        monkeypatch,
        long_answer,
        [{"start": 0.0, "end": 10.0, "text": long_answer, "no_speech_prob": 0.99}],
        decision={"action": "follow_up", "question": "What happens after that?"},
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["is_complete"] is False
    assert result["transcript"] == long_answer


def test_segments_without_no_speech_prob_are_not_flagged(db_session, monkeypatch):
    """Pre-upgrade segment shape (no no_speech_prob key) must never trip the guard."""
    participant = _seed(db_session)
    _patch_io_with_segments(
        monkeypatch,
        "Short but real answer",
        [{"start": 0.0, "end": 2.0, "text": "Short but real answer"}],
        decision={"action": "follow_up", "question": "Tell me more?"},
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert result["transcript"] == "Short but real answer"


def test_typed_punctuation_only_answer_raises(db_session, monkeypatch):
    participant = _seed(db_session)
    _patch_io(monkeypatch)

    with pytest.raises(EmptyTranscriptError):
        process_interview_turn(
            participant.id, None, None, db_session, transcript_override="..."
        )


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


def test_english_interviews_still_get_a_language_instruction():
    """The guide may be written in French while the interview runs in
    English. Returning "" for English left the model with no instruction to
    translate it, so it spoke its own sentences in English and then read the
    guide question out verbatim in French."""
    built = interview_engine._language_instruction("en")

    assert built.strip(), "English must not fall through with no instruction"
    assert "English" in built
    assert "NEVER read a guide question out in its original language" in built


def test_language_instruction_covers_every_supported_language():
    for code, name in interview_engine.LANGUAGE_NAMES.items():
        built = interview_engine._language_instruction(code)
        assert name in built, f"{code} instruction missing its language name"
        assert "translate" in built.lower()


def test_effective_system_prompt_carries_the_english_instruction():
    """The layering path is what actually reaches the model."""
    built = interview_engine._effective_system_prompt(None, "en")
    assert "conduct this entire interview in English" in built


# ── Time budget: spread the guide, don't race it and pad the last topic ──────
#
# Regression cover for a real 60-minute / 7-question interview that reached its
# last guide question at minute 20 and then spent 29 minutes asking 24
# follow-ups on that one topic, because (a) nothing enforced the "you are ahead,
# go deeper" advice, and (b) the close gate advertised to the model was shut
# until 80% of the budget, leaving follow_up as the only legal action.


def test_followup_allowance_scales_with_the_time_budget():
    # A generous per-question budget buys more probing, not a padded last topic.
    assert _followup_allowance(60, 7) > MAX_FOLLOWUPS_PER_QUESTION
    assert _followup_allowance(60, 7) <= MAX_FOLLOWUPS_CEILING
    # A tight budget never drops below the floor.
    assert _followup_allowance(15, 10) == MAX_FOLLOWUPS_PER_QUESTION
    # Even an absurd budget stays bounded, and a misconfigured one is safe.
    assert _followup_allowance(600, 2) == MAX_FOLLOWUPS_CEILING
    assert _followup_allowance(0, 0) == MAX_FOLLOWUPS_PER_QUESTION


def test_close_gate_opens_once_the_guide_is_covered():
    """The gate shown to the model must not be stricter than the host's own.

    While it was, an interview that finished its guide early was told "close is
    NOT available, keep the conversation going" and, with no next question to
    advance to, could only answer with filler follow-ups.
    """
    floor = GUIDE_COVERED_CLOSE_FLOOR_PCT
    assert _close_gate_open(all_questions_done=True, time_used_pct=floor, pacing_known=True)
    # The old gate held until 80%; the whole guide being covered now suffices.
    assert _close_gate_open(all_questions_done=True, time_used_pct=60.0, pacing_known=True)
    # But not so early that a fast run gets no depth at all.
    assert not _close_gate_open(all_questions_done=True, time_used_pct=floor - 10, pacing_known=True)
    # Guide not covered: there is still somewhere to advance to, so stay shut.
    assert not _close_gate_open(all_questions_done=False, time_used_pct=60.0, pacing_known=True)
    # Duration misconfigured: coverage is the only signal left.
    assert _close_gate_open(all_questions_done=True, time_used_pct=0.0, pacing_known=False)
    assert not _close_gate_open(all_questions_done=False, time_used_pct=0.0, pacing_known=False)


def _no_short_run(monkeypatch):
    """Pin the participant as engaged.

    The fixture's seeded answers are two words long, which is itself a
    short-answer run and releases the ahead-of-schedule guard. Tests that
    exercise the guard need an engaged participant, or they pass for the
    wrong reason.
    """
    monkeypatch.setattr(
        interview_engine, "_detect_short_answers", lambda turns: {"is_short_run": False}
    )


def _age(participant, db, *, minutes: float):
    """Backdate the interview so ``minutes`` of active time have elapsed."""
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    participant.started_at = now - timedelta(minutes=minutes)
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    step = minutes / max(len(turns), 1)
    for i, turn in enumerate(turns):
        turn.created_at = now - timedelta(minutes=minutes - step * i)
    db.commit()


def test_racing_ahead_is_held_on_the_current_topic(db_session, monkeypatch):
    """next_question while well ahead of schedule is overridden to follow_up.

    Three of seven questions covered in the first 5 minutes of a 60-minute
    study: advancing again strands the rest of the budget on the last question.
    """
    participant = _seed(db_session, answered_up_to=2, **BIG)
    _age(participant, db_session, minutes=5)  # Angelo was on Q3 of 7 at minute 5
    _no_short_run(monkeypatch)
    calls = _patch_io(
        monkeypatch, decision={"action": "next_question", "question": "Next topic!"}
    )

    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.is_follow_up is True
    assert new_turn.question_index == 2  # held on the current topic
    assert new_turn.question_text == "[regenerated for follow_up]"
    assert any(c.get("forced_action") == "follow_up" for c in calls)


def test_on_schedule_advances_normally(db_session, monkeypatch):
    """The guard must not fire when the interview is pacing correctly."""
    participant = _seed(db_session, answered_up_to=2, **BIG)
    # 3 of 7 questions after 20 of 60 minutes is roughly an even spread.
    _age(participant, db_session, minutes=20)
    _no_short_run(monkeypatch)
    calls = _patch_io(
        monkeypatch, decision={"action": "next_question", "question": "Next topic!"}
    )

    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.is_follow_up is False
    assert new_turn.question_index == 3
    assert not any(c.get("forced_action") for c in calls)


def test_ahead_guard_releases_once_the_topic_allowance_is_spent(db_session, monkeypatch):
    """Holding a topic is bounded: the allowance releases the interview."""
    participant = _seed(
        db_session, answered_up_to=2, followups_on_current=BIG_ALLOWANCE, **BIG
    )
    _age(participant, db_session, minutes=5)  # still far ahead of schedule
    _no_short_run(monkeypatch)
    calls = _patch_io(
        monkeypatch, decision={"action": "next_question", "question": "Next topic!"}
    )

    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.is_follow_up is False
    assert new_turn.question_index == 3
    assert not any(c.get("forced_action") for c in calls)


def test_ahead_guard_releases_on_a_short_answer_run(db_session, monkeypatch):
    """A disengaging participant is not held on a topic they are done with."""
    participant = _seed(db_session, answered_up_to=2, **BIG)
    _age(participant, db_session, minutes=5)
    calls = _patch_io(
        monkeypatch,
        transcript="Not really.",  # short answer, and the seeded ones are short too
        decision={"action": "next_question", "question": "Next topic!"},
    )
    monkeypatch.setattr(
        interview_engine, "_detect_short_answers", lambda turns: {"is_short_run": True}
    )

    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.is_follow_up is False
    assert new_turn.question_index == 3
    assert not any(c.get("forced_action") for c in calls)


def test_endless_probing_on_the_last_question_is_wrapped_up(db_session, monkeypatch):
    """The Angelo case: out of guide, out of things to ask, so wrap up.

    The last question has nowhere to advance to, so a model that keeps choosing
    follow_up would otherwise probe until the clock ran out.
    """
    participant = _seed(
        db_session, answered_up_to=2, followups_on_current=SEEDED_ALLOWANCE
    )
    _age(participant, db_session, minutes=12)  # past the close floor of a 20-min study
    calls = _patch_io(
        monkeypatch, decision={"action": "follow_up", "question": "And beyond that?"}
    )

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    # A forced close routes through the "anything we haven't covered?" check.
    assert result["question_index"] == interview_engine.FINAL_CHECK_QUESTION_INDEX
    assert result["is_complete"] is False
    assert any(c.get("forced_action") == "close" for c in calls)


def test_last_question_still_gets_its_allowance(db_session, monkeypatch):
    """The wrap-up backstop must not cut a rich final topic short."""
    participant = _seed(
        db_session, answered_up_to=2, followups_on_current=SEEDED_ALLOWANCE - 1
    )
    _age(participant, db_session, minutes=12)
    _patch_io(monkeypatch, decision={"action": "follow_up", "question": "And beyond that?"})

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.is_follow_up is True
    assert result["is_complete"] is False


def test_forced_close_without_regeneration_speaks_a_closing(db_session, monkeypatch):
    """The deterministic fallback must not speak a probe while ending the call."""
    participant = _seed(
        db_session, answered_up_to=2, followups_on_current=SEEDED_ALLOWANCE
    )
    _age(participant, db_session, minutes=12)
    _patch_io(monkeypatch)
    # Model reachable for the first decision, unreachable for the regeneration.
    seen: list[dict] = []

    def _decide(*a, **k):
        seen.append(k)
        if k.get("forced_action"):
            raise interview_engine.InterviewAIUnavailable("down")
        return {"action": "follow_up", "question": "And beyond that?", "coaching": None}

    monkeypatch.setattr(interview_engine, "decide_next_action", _decide)
    monkeypatch.setattr(interview_engine, "_cached_tts", lambda text, language=None: None)

    result = process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)

    assert any(c.get("forced_action") == "close" for c in seen)
    spoken = result["question_text"]
    assert spoken == interview_engine._final_check_question("en")
    assert "?" in spoken  # the closing check, never a stale probe


# ---------------------------------------------------------------------------
# Neutral stance: no agreement / praise openers, questions stay questions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, cleaned",
    [
        ("Exactement, et au final, c'est vous qui validez ?", "Et au final, c'est vous qui validez ?"),
        ("Super, exactement. Et la dernière fois, comment ça s'est passé ?", "Et la dernière fois, comment ça s'est passé ?"),
        ("Absolutely! Walk me through the last time that happened.", "Walk me through the last time that happened."),
        ("Très bien. Racontez-moi la dernière fois.", "Racontez-moi la dernière fois."),
        ("Genau, und wie lief das beim letzten Mal ab?", "Und wie lief das beim letzten Mal ab?"),
        # Untouched: not an opener, or the word is part of the sentence.
        ("Right now, what do you do first?", "Right now, what do you do first?"),
        ("Good morning, how did the week start?", "Good morning, how did the week start?"),
        ("Walk me through the last time that happened.", "Walk me through the last time that happened."),
        # Nothing but praise is left alone rather than emptied.
        ("Great!", "Great!"),
    ],
)
def test_leading_evaluation_is_stripped_from_questions(raw, cleaned):
    assert interview_engine._strip_leading_evaluation(raw) == cleaned


def _tool_response(**inp):
    class _Block:
        type = "tool_use"
        input = inp

    class _Resp:
        content = [_Block()]

    return _Resp()


def test_decision_parser_strips_praise_from_follow_ups_and_transitions():
    out = interview_engine._parse_decision_response(
        _tool_response(action="follow_up", question="Exactement, comment ça se passe concrètement ?"), "fr"
    )
    assert out["question"] == "Comment ça se passe concrètement ?"
    out = interview_engine._parse_decision_response(
        _tool_response(action="next_question", question="Perfect. Let's talk about onboarding: how did it go?"), "en"
    )
    assert out["question"] == "Let's talk about onboarding: how did it go?"
    # A wrap-up keeps its warmth.
    out = interview_engine._parse_decision_response(
        _tool_response(action="close", question="Perfect, that wraps it up. Thank you so much."), "en"
    )
    assert out["question"] == "Perfect, that wraps it up. Thank you so much."


def test_prompt_forbids_affirmations_and_demands_a_question():
    prompt = interview_engine.INTERVIEWER_SYSTEM_PROMPT
    assert "Never open with agreement or praise" in prompt
    assert "ends with exactly one open question" in prompt
    desc = interview_engine.DECISION_TOOL["input_schema"]["properties"]["question"]["description"]
    assert "never opens with agreement or praise" in desc


@pytest.mark.parametrize(
    "raw, cleaned",
    [
        ("That validation step idea is useful. Looking ahead, what would need to change for you to hand over more?",
         "Looking ahead, what would need to change for you to hand over more?"),
        ("That eight hours of wrong-track work is a striking cost. When an AI gives you an answer, what makes you rely on it?",
         "When an AI gives you an answer, what makes you rely on it?"),
        ("That overconfidence point is telling. Is there anything else we haven't touched on?",
         "Is there anything else we haven't touched on?"),
        ("The thought process mattering more than the result is clear. Are there decisions where you want a human in the loop?",
         "Are there decisions where you want a human in the loop?"),
        ("Ce point sur la validation est très utile. Qu'est-ce qui devrait changer pour vous ?",
         "Qu'est-ce qui devrait changer pour vous ?"),
        # A reflection in their words is not a verdict: kept.
        ("Eight hours lost. What happened after you restarted?", "Eight hours lost. What happened after you restarted?"),
        ("You said you'd never let it do your taxes. What makes taxes different?",
         "You said you'd never let it do your taxes. What makes taxes different?"),
        # A verdict with no question after it is left alone rather than emptied.
        ("That point is useful.", "That point is useful."),
    ],
)
def test_leading_verdict_sentence_is_stripped_but_reflections_stay(raw, cleaned):
    assert interview_engine._strip_leading_verdict(raw) == cleaned


def test_prompt_follows_the_thread_and_bans_verdicts():
    prompt = interview_engine.INTERVIEWER_SYSTEM_PROMPT
    assert "Following the thread" in prompt
    assert "probe at least once before you move on" in prompt
    assert "REFLECTING, never by JUDGING" in prompt


# ---------------------------------------------------------------------------
# Minimum depth: a topic's first substantive answer gets at least one probe
# ---------------------------------------------------------------------------

RICH_ANSWER = (
    "I am always checking for the full reasoning behind it, if I do not see the thought "
    "process I get skeptical and I go and verify the numbers myself before I use anything."
)


def test_first_substantive_answer_is_probed_before_the_guide_moves_on(db_session, monkeypatch):
    """Replayed against a real transcript the model moved on after one rich
    answer in a third of the topics: the host now holds the topic for one
    probe, with regenerated wording for the forced follow-up."""
    participant = _seed(db_session, followups_on_current=0)
    calls = _patch_io(
        monkeypatch,
        transcript=RICH_ANSWER,
        decision={"action": "next_question", "question": "Moving on: next topic?"},
    )
    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)
    new_turn = sorted(participant.turns, key=lambda t: t.turn_index)[-1]
    assert new_turn.is_follow_up is True
    assert new_turn.question_index == 0
    assert new_turn.question_text == "[regenerated for follow_up]"
    assert any(c.get("forced_action") == "follow_up" for c in calls)


def test_short_or_second_answers_do_not_trigger_the_depth_guard(db_session, monkeypatch):
    # A brief first answer: the model's next_question stands.
    participant = _seed(db_session, followups_on_current=0)
    _patch_io(monkeypatch, transcript="Not really, no.", decision={"action": "next_question", "question": "Next topic?"})
    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)
    assert sorted(participant.turns, key=lambda t: t.turn_index)[-1].question_index == 1


def test_a_rich_answer_to_a_follow_up_does_not_trigger_the_depth_guard(db_session, monkeypatch):
    # The topic has already been probed once: the model's next_question stands.
    participant = _seed(db_session, followups_on_current=1)
    _patch_io(monkeypatch, transcript=RICH_ANSWER, decision={"action": "next_question", "question": "Next topic?"})
    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)
    assert sorted(participant.turns, key=lambda t: t.turn_index)[-1].question_index == 1


def test_depth_guard_yields_when_behind_schedule(db_session, monkeypatch):
    from datetime import datetime, timedelta

    participant = _seed(db_session, followups_on_current=0)
    now = datetime.utcnow()
    # 12 of 20 minutes gone while still on question 0: behind, so a rich
    # first answer no longer holds the topic.
    participant.started_at = now - timedelta(minutes=12)
    for turn in participant.turns:
        turn.created_at = now - timedelta(minutes=12)
    db_session.commit()
    _patch_io(monkeypatch, transcript=RICH_ANSWER, decision={"action": "next_question", "question": "Next topic?"})
    process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)
    assert sorted(participant.turns, key=lambda t: t.turn_index)[-1].question_index == 1


def test_untouched_placeholder_guide_questions_are_not_topics(db_session):
    """A "New question" row the researcher never edited must not become a
    topic the interviewer invents a question for."""
    from app.models.project import InterviewGuideQuestion

    participant = _seed(db_session, question_count=2)
    project = participant.project
    db_session.add(InterviewGuideQuestion(project_id=project.id, section_index=0, section_title="S", question_index=2,
                                          main_question="Nouvelle question", sort_order=99))
    db_session.add(InterviewGuideQuestion(project_id=project.id, section_index=0, section_title="S", question_index=3,
                                          main_question="  New question. ", sort_order=100))
    db_session.commit()
    db_session.refresh(project)
    active = interview_engine._active_guide_questions(project)
    assert len(active) == 2
    assert "Nouvelle question" not in interview_engine._build_interview_guide_str(project)
    ctx = interview_engine.get_interview_context(participant.id, db_session)
    assert ctx["total_questions"] == 2


def test_every_turn_logs_one_decision_line(db_session, monkeypatch, caplog):
    """Pacing and depth are audited from prod logs, not by replaying transcripts."""
    import logging

    participant = _seed(db_session, followups_on_current=0)
    _patch_io(monkeypatch, decision={"action": "follow_up", "question": "Tell me more?", "probe": "specific_moment"})
    with caplog.at_level(logging.INFO, logger="app.services.interview_engine"):
        process_interview_turn(participant.id, "audio/x.mp3", "/audio/x.mp3", db_session)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("interview decision")]
    assert len(lines) == 1
    line = lines[0]
    assert f"participant={participant.id}" in line
    assert "action=follow_up model=follow_up forced=-" in line
    assert "probe=specific_moment" in line
    assert "followups=0/" in line and "pace=" in line and "live=False" in line
