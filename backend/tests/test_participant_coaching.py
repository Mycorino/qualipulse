"""Participant coaching (PF-3 follow-ups) + transcript echo on /respond.

Covers: short-answer run detection (incl. run starts), the participant-facing
hint gate (fires at run start, capped per interview), coaching-text
sanitization, and the transcript field flowing through TurnResponse on both
the fresh-processing and dedupe paths.
"""
from types import SimpleNamespace

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.services.interview_engine import (
    MAX_COACHING_HINTS,
    SHORT_ANSWER_RUN,
    _coaching_hint_for,
    _detect_short_answers,
    _sanitize_coaching,
    _should_show_coaching,
)


def _turn(text):
    return SimpleNamespace(response_transcript=text)


SHORT = "yes maybe"
LONG = " ".join(["word"] * 30)


# ── _detect_short_answers ────────────────────────────────────────────────────

def test_no_answers_is_not_a_short_run():
    state = _detect_short_answers([_turn(None), _turn("   "), _turn("[Skipped]")])
    assert state == {
        "is_short_run": False,
        "last_words": None,
        "run_length": 0,
        "is_run_start": False,
        "run_starts": 0,
    }


def test_single_short_answer_does_not_flag():
    state = _detect_short_answers([_turn(LONG), _turn(SHORT)])
    assert not state["is_short_run"]
    assert state["run_length"] == 1
    assert state["run_starts"] == 0


def test_run_start_flagged_at_threshold():
    state = _detect_short_answers([_turn(LONG), _turn(SHORT), _turn(SHORT)])
    assert state["is_short_run"]
    assert state["is_run_start"]
    assert state["run_length"] == SHORT_ANSWER_RUN
    assert state["run_starts"] == 1


def test_continuing_run_is_not_a_start():
    state = _detect_short_answers([_turn(SHORT), _turn(SHORT), _turn(SHORT)])
    assert state["is_short_run"]
    assert not state["is_run_start"]
    assert state["run_length"] == 3
    assert state["run_starts"] == 1


def test_long_answer_resets_and_second_run_counts():
    turns = [_turn(SHORT), _turn(SHORT), _turn(LONG), _turn(SHORT), _turn(SHORT)]
    state = _detect_short_answers(turns)
    assert state["is_short_run"]
    assert state["is_run_start"]
    assert state["run_starts"] == 2


def test_skipped_turns_excluded_from_runs():
    turns = [_turn(SHORT), _turn("[Skipped]"), _turn(SHORT)]
    state = _detect_short_answers(turns)
    # the skip is invisible, so the two short answers form one run
    assert state["is_short_run"]
    assert state["run_starts"] == 1


# ── hint gate ────────────────────────────────────────────────────────────────

def test_gate_fires_only_at_run_start():
    start = _detect_short_answers([_turn(SHORT), _turn(SHORT)])
    continuing = _detect_short_answers([_turn(SHORT), _turn(SHORT), _turn(SHORT)])
    assert _should_show_coaching(start)
    assert not _should_show_coaching(continuing)


def test_gate_caps_hints_per_interview():
    # MAX_COACHING_HINTS runs already shown → the next run start is silent.
    turns = []
    for _ in range(MAX_COACHING_HINTS + 1):
        turns += [_turn(SHORT), _turn(SHORT), _turn(LONG)]
    # drop the trailing long answer so the last run is current + a start
    turns = turns[:-1]
    state = _detect_short_answers(turns)
    assert state["is_run_start"]
    assert state["run_starts"] == MAX_COACHING_HINTS + 1
    assert not _should_show_coaching(state)


# ── static hint + sanitizer ──────────────────────────────────────────────────

def test_static_hint_localized_and_gated():
    state = {"is_short_run": True}
    assert "moments" in _coaching_hint_for(state, "en")
    assert "concrets" in _coaching_hint_for(state, "fr")
    assert _coaching_hint_for(state, "xx") == _coaching_hint_for(state, "en")
    assert _coaching_hint_for({"is_short_run": False}, "en") is None


def test_sanitize_coaching():
    assert _sanitize_coaching("  A   short\n tip. ") == "A short tip."
    assert _sanitize_coaching("") is None
    assert _sanitize_coaching("   ") is None
    assert _sanitize_coaching(None) is None
    assert _sanitize_coaching({"not": "a string"}) is None
    assert _sanitize_coaching("x" * 241) is None
    assert _sanitize_coaching("x" * 240) == "x" * 240


# ── /respond returns the transcript ─────────────────────────────────────────

def _seed_interview(db_session, with_answered_turn=False):
    company = Company(name="Acme", email="owner@acme.com", password_hash="x", email_verified=True)
    db_session.add(company)
    db_session.flush()
    project = Project(company_id=company.id, name="Study", language="en")
    db_session.add(project)
    db_session.flush()
    link = InterviewLink(project_id=project.id, token="tok-coaching", is_active=True)
    db_session.add(link)
    db_session.flush()
    participant = Participant(link_id=link.id, project_id=project.id, status="in_progress")
    db_session.add(participant)
    db_session.flush()
    if with_answered_turn:
        db_session.add(
            InterviewTurn(
                participant_id=participant.id,
                turn_index=0,
                question_index=0,
                question_text="Q1?",
                response_transcript="what we heard before",
            )
        )
    db_session.commit()
    return link, participant


def test_respond_returns_transcript_and_coaching(client, db_session, monkeypatch):
    link, participant = _seed_interview(db_session)

    from app.routers import interview as interview_router

    monkeypatch.setattr(interview_router, "upload_audio", lambda data, key: "http://x/a.webm")
    monkeypatch.setattr(interview_router, "needs_transcode", lambda ext: False)
    monkeypatch.setattr(
        interview_router,
        "process_interview_turn",
        lambda pid, key, url, db: {
            "question_text": "Next question?",
            "tts_audio_url": None,
            "is_complete": False,
            "is_follow_up": False,
            "question_index": 1,
            "elapsed_seconds": 30,
            "total_seconds": 600,
            "coaching_hint": "If a story comes to mind, share it.",
            "transcript": "I use it every day on my commute",
        },
    )

    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        files={"audio": ("recording.webm", b"0" * 1000, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transcript"] == "I use it every day on my commute"
    assert body["coaching_hint"] == "If a story comes to mind, share it."


def test_respond_dedupe_path_returns_cached_transcript(client, db_session):
    link, participant = _seed_interview(db_session, with_answered_turn=True)

    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        files={"audio": ("recording.webm", b"0" * 1000, "audio/webm")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["question_text"] == "Q1?"
    assert body["transcript"] == "what we heard before"
