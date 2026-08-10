"""Accessibility text fallback on /respond.

Participants without a working microphone can type their answer instead of
recording it. Covers: the exactly-one-of audio/text contract (400 otherwise),
the typed path skipping STT/upload entirely and flowing the text into
process_interview_turn as transcript_override, empty typed answers mirroring
the empty-transcript response shape (422), the max-length cap, and, via the
real engine's warm-up short-circuit, that a typed answer lands on the turn as
response_transcript with a NULL audio_recording_url.
"""
from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.routers.interview import MAX_TEXT_ANSWER_CHARS


def _seed_interview(db_session, warmup_turn=False):
    company = Company(name="Acme", email="owner@acme.com", password_hash="x", email_verified=True)
    db_session.add(company)
    db_session.flush()
    project = Project(company_id=company.id, name="Study", language="en")
    db_session.add(project)
    db_session.flush()
    link = InterviewLink(project_id=project.id, token="tok-text-fallback", is_active=True)
    db_session.add(link)
    db_session.flush()
    participant = Participant(link_id=link.id, project_id=project.id, status="in_progress")
    db_session.add(participant)
    db_session.flush()
    if warmup_turn:
        # Warm-up question awaiting an answer (question_index = -1) — lets the
        # real engine run without a Claude call (warm-up handoff short-circuit).
        db_session.add(
            InterviewTurn(
                participant_id=participant.id,
                turn_index=0,
                question_index=-1,
                question_text="Just to warm up, how is your day going?",
            )
        )
    db_session.commit()
    return link, participant


_ENGINE_RESULT = {
    "question_text": "Next question?",
    "tts_audio_url": None,
    "is_complete": False,
    "is_follow_up": False,
    "question_index": 1,
    "elapsed_seconds": 30,
    "total_seconds": 600,
    "coaching_hint": None,
    "transcript": None,
}


def test_text_only_flows_as_transcript_override(client, db_session, monkeypatch):
    """Text path: no upload, engine receives the text with null audio args."""
    link, participant = _seed_interview(db_session)

    from app.routers import interview as interview_router

    calls = {}

    def fake_process(pid, key, url, db, transcript_override=None):
        calls["args"] = (pid, key, url, transcript_override)
        return {**_ENGINE_RESULT, "transcript": transcript_override}

    monkeypatch.setattr(interview_router, "process_interview_turn", fake_process)
    # The typed path must never touch audio storage or transcoding.
    monkeypatch.setattr(
        interview_router, "upload_audio",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("upload_audio called on text path")),
    )
    monkeypatch.setattr(
        interview_router, "needs_transcode",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("needs_transcode called on text path")),
    )

    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        data={"text": "  I mostly use it on my commute.  "},
    )
    assert r.status_code == 200, r.text
    assert calls["args"] == (participant.id, None, None, "I mostly use it on my commute.")
    assert r.json()["transcript"] == "I mostly use it on my commute."


def test_text_answer_saved_on_turn_with_null_audio_url(client, db_session, monkeypatch):
    """Real engine (warm-up short-circuit): the turn stores the typed text and
    audio_recording_url stays NULL."""
    link, participant = _seed_interview(db_session, warmup_turn=True)

    from app.services import interview_engine as engine

    # Stub only the TTS side effects; the transcript-save path runs for real.
    monkeypatch.setattr(engine, "generate_speech", lambda text: b"mp3")
    monkeypatch.setattr(engine, "upload_audio", lambda data, key: "http://x/tts.mp3")

    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        data={"text": "Pretty good, thanks for asking."},
    )
    assert r.status_code == 200, r.text

    db_session.expire_all()
    turns = sorted(participant.turns, key=lambda t: t.turn_index)
    answered = turns[0]
    assert answered.response_transcript == "Pretty good, thanks for asking."
    assert answered.audio_recording_url is None
    # The warm-up handoff queued the first real question as a new turn.
    assert len(turns) == 2


def test_both_audio_and_text_rejected(client, db_session):
    link, participant = _seed_interview(db_session)
    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        files={"audio": ("recording.webm", b"0" * 100, "audio/webm")},
        data={"text": "also typed"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "audio_or_text_required"


def test_neither_audio_nor_text_rejected(client, db_session):
    link, participant = _seed_interview(db_session)
    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        data={"unrelated": "field"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "audio_or_text_required"


def test_empty_text_mirrors_empty_transcript_shape(client, db_session):
    link, participant = _seed_interview(db_session)
    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        data={"text": "   \n  "},
    )
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "empty_transcript"
    assert detail["message"]


def test_text_over_max_length_rejected(client, db_session):
    link, participant = _seed_interview(db_session)
    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        data={"text": "x" * (MAX_TEXT_ANSWER_CHARS + 1)},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "text_too_long"
