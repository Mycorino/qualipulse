"""Turn-index reconciliation, the /finish control, and the profile patch.

These cover the participant-facing failure mode that used to silently
corrupt data: a client that times out, retries, and has its answer accepted
against a question the participant never heard.
"""

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import InterviewGuideQuestion, Project


def _seed(db, *, token="tok-sync", questions=("Q one?", "Q two?")):
    company = Company(name="Acme", email=f"{token}@acme.com", password_hash="x", email_verified=True)
    db.add(company)
    db.flush()
    project = Project(company_id=company.id, name="Study", language="en", interview_duration_minutes=20)
    db.add(project)
    db.flush()
    for i, q in enumerate(questions):
        db.add(
            InterviewGuideQuestion(
                project_id=project.id, section_index=0, section_title="Main",
                question_index=i, main_question=q, sort_order=i,
            )
        )
    link = InterviewLink(project_id=project.id, token=token, is_active=True)
    db.add(link)
    db.flush()
    participant = Participant(link_id=link.id, project_id=project.id, status="in_progress")
    db.add(participant)
    db.flush()
    return link, participant


def _patch_router(monkeypatch, result=None):
    from app.routers import interview as r

    monkeypatch.setattr(r, "upload_audio", lambda data, key: "http://x/a.mp3")
    monkeypatch.setattr(r, "needs_transcode", lambda ext: False)
    if result is not None:
        monkeypatch.setattr(
            r, "process_interview_turn",
            lambda pid, key, url, db, *a, **k: dict(result),
        )


def test_stale_turn_index_is_rejected_not_misattributed(client, db_session, monkeypatch):
    """A retry aimed at an already-answered turn must never be accepted as
    the answer to the question that followed it."""
    link, participant = _seed(db_session, token="tok-stale")
    db_session.add_all([
        InterviewTurn(
            participant_id=participant.id, turn_index=0, question_index=0,
            question_text="Q one?", response_transcript="my first answer",
        ),
        InterviewTurn(
            participant_id=participant.id, turn_index=1, question_index=1,
            question_text="Q two?", tts_audio_url="http://x/q2.mp3",
        ),
    ])
    db_session.commit()
    _patch_router(monkeypatch, result={"question_text": "should not happen", "tts_audio_url": None,
                                       "is_complete": False, "turn_index": 99, "transcript": "x"})

    # The client retries turn 0 after its own timeout: the server already
    # processed it, so it replays the question that followed.
    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        files={"audio": ("recording.webm", b"0" * 1000, "audio/webm")},
        data={"turn_index": "0"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["question_text"] == "Q two?"
    assert body["turn_index"] == 1
    assert body["transcript"] == "my first answer"

    # And no phantom turn was created.
    db_session.refresh(participant)
    assert len(participant.turns) == 2


def test_unknown_turn_index_returns_409_with_current_state(client, db_session, monkeypatch):
    link, participant = _seed(db_session, token="tok-409")
    db_session.add(
        InterviewTurn(
            participant_id=participant.id, turn_index=0, question_index=0,
            question_text="Q one?", tts_audio_url="http://x/q1.mp3",
        )
    )
    db_session.commit()
    _patch_router(monkeypatch, result={"question_text": "nope", "tts_audio_url": None,
                                       "is_complete": False, "turn_index": 1})

    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        files={"audio": ("recording.webm", b"0" * 1000, "audio/webm")},
        data={"turn_index": "7"},
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["code"] == "turn_mismatch"
    assert detail["current"]["question_text"] == "Q one?"
    assert detail["current"]["turn_index"] == 0


def test_matching_turn_index_processes_normally(client, db_session, monkeypatch):
    link, participant = _seed(db_session, token="tok-match")
    db_session.add(
        InterviewTurn(
            participant_id=participant.id, turn_index=0, question_index=0, question_text="Q one?",
        )
    )
    db_session.commit()
    _patch_router(monkeypatch, result={
        "question_text": "Q two?", "tts_audio_url": None, "is_complete": False,
        "is_follow_up": False, "question_index": 1, "turn_index": 1,
        "elapsed_seconds": 10, "total_seconds": 1200, "transcript": "answered",
    })

    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        files={"audio": ("recording.webm", b"0" * 1000, "audio/webm")},
        data={"turn_index": "0"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["turn_index"] == 1


def test_finish_endpoint_completes_and_is_idempotent(client, db_session, monkeypatch):
    from app.services import interview_engine

    link, participant = _seed(db_session, token="tok-finish")
    db_session.add_all([
        InterviewTurn(
            participant_id=participant.id, turn_index=0, question_index=0,
            question_text="Q one?", response_transcript="a real answer here",
        ),
        InterviewTurn(
            participant_id=participant.id, turn_index=1, question_index=1, question_text="Q two?",
        ),
    ])
    db_session.commit()
    monkeypatch.setattr(interview_engine, "_cached_tts", lambda text, language=None: None)
    monkeypatch.setattr(interview_engine, "_spawn_completion_side_effects", lambda pid: None)

    r1 = client.post(f"/interview/{link.token}/{participant.id}/finish")
    assert r1.status_code == 200, r1.text
    assert r1.json()["is_complete"] is True

    r2 = client.post(f"/interview/{link.token}/{participant.id}/finish")
    assert r2.status_code == 200
    assert r2.json()["turn_index"] == r1.json()["turn_index"]

    db_session.refresh(participant)
    assert participant.status == "completed"
    assert participant.completion_reason == "participant_finished"


def test_profile_patch_saves_demographics_without_session(client, db_session):
    link, participant = _seed(db_session, token="tok-profile")
    db_session.commit()

    r = client.patch(
        f"/interview/{link.token}/{participant.id}/profile",
        json={"display_name": "Sam", "age_range": "25-34", "country": "France",
              "profession": "Designer", "email": "Sam@Example.com "},
    )
    assert r.status_code == 200, r.text
    db_session.refresh(participant)
    assert participant.display_name == "Sam"
    assert participant.age_range == "25-34"
    assert participant.country == "France"
    assert participant.profession == "Designer"
    assert participant.email == "sam@example.com"
    assert participant.email_verified is False


def test_profile_patch_never_overwrites_a_verified_email(client, db_session):
    link, participant = _seed(db_session, token="tok-profile2")
    participant.email = "verified@example.com"
    participant.email_verified = True
    db_session.commit()

    r = client.patch(
        f"/interview/{link.token}/{participant.id}/profile",
        json={"email": "attacker@example.com"},
    )
    assert r.status_code == 200
    db_session.refresh(participant)
    assert participant.email == "verified@example.com"
    assert participant.email_verified is True


def test_turn_audio_is_generated_once_and_cached(client, db_session, monkeypatch):
    """Deferred TTS: first call synthesises, second reuses the stored URL."""
    from app.services import interview_engine

    link, participant = _seed(db_session, token="tok-audio")
    db_session.add(
        InterviewTurn(
            participant_id=participant.id, turn_index=0, question_index=0,
            question_text="Q one?",
        )
    )
    db_session.commit()

    calls = []
    monkeypatch.setattr(
        interview_engine, "generate_speech",
        lambda text, language=None: calls.append(text) or b"mp3",
    )
    monkeypatch.setattr(interview_engine, "upload_audio", lambda data, key: f"/audio/{key}")

    r1 = client.get(f"/interview/{link.token}/{participant.id}/turn-audio?turn_index=0")
    assert r1.status_code == 200, r1.text
    assert r1.json()["tts_audio_url"].startswith("/audio/tts/")

    r2 = client.get(f"/interview/{link.token}/{participant.id}/turn-audio?turn_index=0")
    assert r2.json()["tts_audio_url"] == r1.json()["tts_audio_url"]
    assert len(calls) == 1


def test_turn_audio_degrades_to_null_when_tts_fails(client, db_session, monkeypatch):
    from app.services import interview_engine

    link, participant = _seed(db_session, token="tok-audio-fail")
    db_session.add(
        InterviewTurn(
            participant_id=participant.id, turn_index=0, question_index=0,
            question_text="Q one?",
        )
    )
    db_session.commit()

    def _boom(text, language=None):
        raise RuntimeError("tts down")

    monkeypatch.setattr(interview_engine, "generate_speech", _boom)

    r = client.get(f"/interview/{link.token}/{participant.id}/turn-audio?turn_index=0")
    assert r.status_code == 200
    assert r.json()["tts_audio_url"] is None


def test_skip_rejects_a_stale_turn_index(client, db_session):
    link, participant = _seed(db_session, token="tok-skip-stale")
    db_session.add_all([
        InterviewTurn(
            participant_id=participant.id, turn_index=0, question_index=0,
            question_text="Q one?", response_transcript="answered",
        ),
        InterviewTurn(
            participant_id=participant.id, turn_index=1, question_index=1, question_text="Q two?",
        ),
    ])
    db_session.commit()

    r = client.post(
        f"/interview/{link.token}/{participant.id}/skip", json={"turn_index": 0}
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "turn_mismatch"
    assert r.json()["detail"]["current"]["turn_index"] == 1


def test_completed_interview_replays_instead_of_400(client, db_session):
    """A lost 200 on the final turn must not strand the participant.

    The client keeps the blob and retries; returning 400 left them tapping
    Submit against an error forever, never reaching the completion screen.
    """
    link, participant = _seed(db_session, token="tok-done")
    participant.status = "completed"
    db_session.add(
        InterviewTurn(
            participant_id=participant.id, turn_index=2, question_index=1,
            question_text="That wraps it up, thank you!", tts_audio_url="http://x/bye.mp3",
        )
    )
    db_session.commit()

    r = client.post(
        f"/interview/{link.token}/{participant.id}/respond",
        files={"audio": ("recording.webm", b"0" * 1000, "audio/webm")},
        data={"turn_index": "1"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_complete"] is True
    assert body["question_text"] == "That wraps it up, thank you!"
