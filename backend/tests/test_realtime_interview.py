"""Realtime interview beta.

Covers the routing layer (mode flag exposure, endpoint gating, session
recording upload) and the sideband bridge's turn handling, with the OpenAI
Realtime transport mocked out — the live WebRTC/WebSocket path can only be
exercised against the real service.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import Project
from app.services import realtime_interview as rt


@pytest.fixture
def bridge_sessions(db_session):
    """Point session_scope() (used by the bridge's own sessions) at the
    per-test in-memory database instead of the dev SQLite file."""
    import app.database as database

    factory = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    with patch.object(database, "SessionLocal", factory):
        yield


def _seed(db, token="tok-rt", *, mode="realtime_beta", turns=1):
    company = Company(
        name="Acme", email=f"{token}@acme.com", password_hash="x", email_verified=True
    )
    db.add(company)
    db.flush()
    project = Project(
        company_id=company.id,
        name="Study",
        language="en",
        interview_duration_minutes=20,
        interview_mode=mode,
    )
    db.add(project)
    db.flush()
    link = InterviewLink(project_id=project.id, token=token, is_active=True)
    db.add(link)
    db.flush()
    participant = Participant(link_id=link.id, project_id=project.id, status="in_progress")
    db.add(participant)
    db.flush()
    for i in range(turns):
        db.add(
            InterviewTurn(
                participant_id=participant.id,
                turn_index=i,
                question_index=i,
                question_text=f"Question {i}?",
                response_transcript="an answer" if i < turns - 1 else None,
            )
        )
    db.commit()
    return link, participant


class TestModeFlag:
    def test_projects_default_to_classic(self, db_session):
        _, participant = _seed(db_session, "tok-default", mode="classic")
        project = participant.project
        assert project.interview_mode == "classic"

    def test_public_link_payload_exposes_the_mode(self, client, db_session):
        link, _ = _seed(db_session, "tok-expose")
        res = client.get(f"/interview/{link.token}")
        assert res.status_code == 200
        assert res.json()["interview_mode"] == "realtime_beta"

    def test_kill_switch_forces_classic_in_the_public_payload(self, client, db_session):
        link, _ = _seed(db_session, "tok-kill")
        with patch.object(settings, "REALTIME_INTERVIEW_ENABLED", False):
            res = client.get(f"/interview/{link.token}")
        assert res.json()["interview_mode"] == "classic"

    def test_settings_patch_updates_and_validates_the_mode(self, client, auth_headers, registered_company):
        res = client.post(
            "/projects/",
            json={
                "name": "Mode study",
                "questions": [
                    {"section_index": 0, "section_title": "S", "question_index": 0, "main_question": "Why?"}
                ],
            },
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        project_id = res.json()["id"]
        assert res.json()["interview_mode"] == "classic"

        res = client.patch(
            f"/projects/{project_id}/settings",
            json={"interview_mode": "realtime_beta"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["interview_mode"] == "realtime_beta"

        res = client.patch(
            f"/projects/{project_id}/settings",
            json={"interview_mode": "warp-speed"},
            headers=auth_headers,
        )
        assert res.status_code == 422


class TestSdpEndpoint:
    def test_rejected_for_classic_studies(self, client, db_session):
        link, participant = _seed(db_session, "tok-classic-sdp", mode="classic")
        res = client.post(
            f"/interview/{link.token}/{participant.id}/realtime/sdp",
            content="v=0\r\n",
            headers={"Content-Type": "application/sdp"},
        )
        assert res.status_code == 404

    def test_rejects_a_body_that_is_not_sdp(self, client, db_session):
        link, participant = _seed(db_session, "tok-bad-sdp")
        res = client.post(
            f"/interview/{link.token}/{participant.id}/realtime/sdp",
            content="{\"not\": \"sdp\"}",
            headers={"Content-Type": "application/sdp"},
        )
        assert res.status_code == 422

    def test_proxies_the_exchange_and_spawns_the_sideband(self, client, db_session):
        link, participant = _seed(db_session, "tok-good-sdp")
        spawned = {}

        def fake_create(sdp_offer, session_config):
            assert sdp_offer.startswith("v=0")
            # SDP must keep/gain its terminating newline: OpenAI rejects an
            # offer without one ("failed to unmarshal SDP: EOF").
            assert sdp_offer.endswith("\n")
            assert session_config["model"] == settings.REALTIME_MODEL
            td = session_config["audio"]["input"]["turn_detection"]
            assert td["create_response"] is False
            return "v=0\r\nanswer", "rtc_test123"

        def fake_spawn(call_id, participant_id, total_minutes):
            spawned.update(call_id=call_id, participant_id=participant_id, total=total_minutes)

        with patch("app.services.realtime_interview.create_realtime_call", fake_create), \
             patch("app.services.realtime_interview.spawn_sideband", fake_spawn):
            res = client.post(
                f"/interview/{link.token}/{participant.id}/realtime/sdp",
                content="v=0\r\noffer",
                headers={"Content-Type": "application/sdp"},
            )

        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/sdp")
        assert res.text == "v=0\r\nanswer"
        # The client restores VAD from this after a mic pause.
        td = json.loads(res.headers["x-realtime-turn-detection"])
        assert td["create_response"] is False
        assert spawned == {"call_id": "rtc_test123", "participant_id": participant.id, "total": 20}

    def test_completed_interviews_cannot_open_a_session(self, client, db_session):
        link, participant = _seed(db_session, "tok-done-sdp")
        participant.status = "completed"
        db_session.commit()
        res = client.post(
            f"/interview/{link.token}/{participant.id}/realtime/sdp",
            content="v=0\r\n",
            headers={"Content-Type": "application/sdp"},
        )
        assert res.status_code == 409


class TestSessionRecording:
    def test_upload_stores_and_exposes_the_recording(self, client, db_session):
        link, participant = _seed(db_session, "tok-rec")
        data = b"a" * 2048

        with patch("app.services.storage.upload_audio", return_value="/audio/recordings/x/session.mp3"), \
             patch("app.services.transcode.needs_transcode", return_value=False):
            res = client.post(
                f"/interview/{link.token}/{participant.id}/realtime/recording",
                files={"audio": ("session.webm", data, "audio/webm")},
            )

        assert res.status_code == 200
        assert res.json()["session_recording_url"] == "/audio/recordings/x/session.mp3"
        db_session.refresh(participant)
        assert participant.session_recording_url == "/audio/recordings/x/session.mp3"

    def test_reupload_replaces_and_deletes_the_superseded_file(self, client, db_session):
        """Incremental uploads must not litter R2 with unreferenced files."""
        link, participant = _seed(db_session, "tok-rec-again")
        participant.session_recording_url = "/audio/recordings/x/old.mp3"
        db_session.commit()
        deleted = []

        with patch("app.services.storage.upload_audio", return_value="/audio/recordings/x/new.mp3"), \
             patch("app.services.storage.delete_audio_by_url", side_effect=deleted.append), \
             patch("app.services.transcode.needs_transcode", return_value=False):
            res = client.post(
                f"/interview/{link.token}/{participant.id}/realtime/recording",
                files={"audio": ("session.webm", b"a" * 2048, "audio/webm")},
            )

        assert res.status_code == 200
        db_session.refresh(participant)
        assert participant.session_recording_url == "/audio/recordings/x/new.mp3"
        assert deleted == ["/audio/recordings/x/old.mp3"]

    def test_tiny_uploads_are_rejected(self, client, db_session):
        link, participant = _seed(db_session, "tok-rec-tiny")
        res = client.post(
            f"/interview/{link.token}/{participant.id}/realtime/recording",
            files={"audio": ("session.webm", b"xx", "audio/webm")},
        )
        assert res.status_code == 422

    def test_classic_studies_have_no_recording_endpoint(self, client, db_session):
        link, participant = _seed(db_session, "tok-rec-classic", mode="classic")
        res = client.post(
            f"/interview/{link.token}/{participant.id}/realtime/recording",
            files={"audio": ("session.webm", b"a" * 2048, "audio/webm")},
        )
        assert res.status_code == 404


class TestBridgeTurns:
    def test_advance_turn_feeds_the_shared_engine(self, db_session, bridge_sessions):
        """The bridge rides transcript_override: same guards, same schema."""
        _, participant = _seed(db_session, "tok-bridge", turns=1)

        with patch(
            "app.services.interview_engine.decide_next_action",
            return_value={"action": "follow_up", "question": "Tell me more?", "coaching": None},
        ):
            result = rt._advance_turn(participant.id, "We mostly use spreadsheets.")

        assert result is not None
        assert result["question_text"] == "Tell me more?"
        assert result["is_complete"] is False

        db_session.expire_all()
        turns = sorted(participant.turns, key=lambda t: t.turn_index)
        assert turns[0].response_transcript == "We mostly use spreadsheets."
        assert turns[-1].question_text == "Tell me more?"
        # Realtime turns never synthesize server-side TTS.
        assert turns[-1].tts_audio_url is None

    def test_silent_transcripts_do_not_advance(self, db_session, bridge_sessions):
        _, participant = _seed(db_session, "tok-bridge-silent", turns=1)
        result = rt._advance_turn(participant.id, "...")
        assert result is None
        db_session.expire_all()
        assert len(participant.turns) == 1

    def test_pending_question_is_the_unanswered_turn(self, db_session, bridge_sessions):
        _, participant = _seed(db_session, "tok-pending", turns=2)
        assert rt._pending_question(participant.id) == "Question 1?"

    def test_usage_logging_prices_audio_and_text_tokens(self, db_session, bridge_sessions):
        _, participant = _seed(db_session, "tok-usage")
        usage = {
            "input_tokens": 1300,
            "output_tokens": 500,
            "input_token_details": {
                "audio_tokens": 1000,
                "text_tokens": 300,
                "cached_tokens_details": {"audio_tokens": 400, "text_tokens": 100},
            },
            "output_token_details": {"audio_tokens": 450, "text_tokens": 50},
        }
        rt._log_realtime_usage(participant.id, usage)

        from app.models.usage import AIUsageLog

        row = (
            db_session.query(AIUsageLog)
            .filter(AIUsageLog.participant_id == participant.id)
            .one()
        )
        assert row.operation == "realtime_interview"
        assert row.model == settings.REALTIME_MODEL
        assert row.input_tokens == 1300
        assert row.output_tokens == 500
        expected = (
            600 * 32 / 1e6      # uncached audio in
            + 400 * 0.40 / 1e6  # cached audio in
            + 200 * 4 / 1e6     # uncached text in
            + 100 * 0.40 / 1e6  # cached text in
            + 450 * 64 / 1e6    # audio out
            + 50 * 16 / 1e6     # text out
        )
        assert abs(row.cost_usd - expected) < 1e-9

    def test_echo_of_the_interviewers_own_line_is_dropped(self, db_session, bridge_sessions):
        """Speakers leak into the mic: the question must never come back as
        the participant's answer and reach Claude."""
        _, participant = _seed(db_session, "tok-echo", turns=1)
        bridge = rt.SidebandBridge("rtc_echo", participant.id, 20)
        bridge.last_spoken = "Qu'est-ce qui vous a poussé à changer d'outil cette année ?"
        bridge.response_active = True

        assert bridge._is_echo("Qu'est-ce qui vous a poussé à changer d'outil cette année") is True
        # A real answer during the same window is not echo.
        assert bridge._is_echo("On a changé parce que la facturation était devenue ingérable") is False
        # Once the interviewer has been quiet a while, nothing is echo.
        bridge.response_active = False
        bridge.last_response_ended_at = 0.0
        assert bridge._is_echo("Qu'est-ce qui vous a poussé à changer d'outil cette année") is False

    def test_short_answers_are_never_mistaken_for_echo(self, db_session, bridge_sessions):
        _, participant = _seed(db_session, "tok-echo-short", turns=1)
        bridge = rt.SidebandBridge("rtc_short", participant.id, 20)
        bridge.last_spoken = "Est-ce que vous utilisez cet outil toutes les semaines ?"
        bridge.response_active = True
        # Content-word overlap only, so filler words in a real answer do not
        # trip the guard.
        assert bridge._is_echo("Oui") is False
        assert bridge._is_echo("Oui, tous les jours en fait") is False

    def test_barge_in_is_off_so_the_interviewer_cannot_cut_itself_off(self, db_session):
        _, participant = _seed(db_session, "tok-barge")
        cfg = rt.build_session_config(participant.project, participant, "fr")
        assert cfg["audio"]["input"]["turn_detection"]["interrupt_response"] is False

    def test_session_config_carries_language_and_vad(self, db_session):
        _, participant = _seed(db_session, "tok-config")
        cfg = rt.build_session_config(participant.project, participant, "fr")
        assert cfg["audio"]["input"]["transcription"]["language"] == "fr"
        assert cfg["audio"]["input"]["turn_detection"]["create_response"] is False
        assert "verbatim" in cfg["instructions"].lower() or "exact" in cfg["instructions"].lower()
        assert json.dumps(cfg)  # serialisable
