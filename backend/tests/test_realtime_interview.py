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


class _FakeWs:
    """Sideband stand-in: hands out queued events, times out otherwise."""

    def __init__(self, events=None, delay_calls=0):
        self.sent = []
        self.events = list(events or [])
        self.delay_calls = delay_calls

    def send(self, payload):
        self.sent.append(json.loads(payload))

    def recv(self, timeout=None):
        import time

        time.sleep(0.01)
        if self.delay_calls > 0:
            self.delay_calls -= 1
            raise TimeoutError
        if self.events:
            return json.dumps(self.events.pop(0))
        raise TimeoutError


@pytest.fixture
def bridge_sessions(db_session):
    """Point session_scope() (used by the bridge's own sessions) at the
    per-test in-memory database instead of the dev SQLite file."""
    import app.database as database

    factory = sessionmaker(bind=db_session.get_bind(), autocommit=False, autoflush=False)
    with patch.object(database, "SessionLocal", factory):
        yield


def _seed(db, token="tok-rt", *, mode="realtime_beta", turns=1, beta=True):
    company = Company(
        name="Acme", email=f"{token}@acme.com", password_hash="x", email_verified=True,
        beta_features_enabled=beta,
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

        client.patch("/auth/me", json={"beta_features_enabled": True}, headers=auth_headers)
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


class TestBetaOptIn:
    """The beta transport is invisible and unreachable without the
    workspace-level opt-in, whatever a study's stored flag says."""

    def test_participant_payload_falls_back_to_classic_without_opt_in(self, client, db_session):
        link, _ = _seed(db_session, "tok-nobeta", beta=False)
        res = client.get(f"/interview/{link.token}")
        assert res.status_code == 200
        assert res.json()["interview_mode"] == "classic"

    def test_realtime_endpoints_404_without_opt_in(self, client, db_session):
        link, participant = _seed(db_session, "tok-nobeta-sdp", beta=False)
        res = client.post(
            f"/interview/{link.token}/{participant.id}/realtime/sdp",
            content="v=0\r\n",
            headers={"Content-Type": "application/sdp"},
        )
        assert res.status_code == 404

    def test_turning_beta_off_reverts_live_studies(self, client, db_session):
        """A workspace leaving the beta must not strand participants on a
        transport the account no longer wants."""
        link, participant = _seed(db_session, "tok-beta-off")
        assert client.get(f"/interview/{link.token}").json()["interview_mode"] == "realtime_beta"

        participant.project.company.beta_features_enabled = False
        db_session.commit()

        assert client.get(f"/interview/{link.token}").json()["interview_mode"] == "classic"
        # The study's own setting is untouched, so re-joining the beta
        # restores it without reconfiguring anything.
        assert participant.project.interview_mode == "realtime_beta"

    def test_settings_patch_refuses_realtime_without_opt_in(self, client, auth_headers, db_session):
        res = client.post(
            "/projects/",
            json={"name": "Gated", "questions": [
                {"section_index": 0, "section_title": "S", "question_index": 0, "main_question": "Why?"}
            ]},
            headers=auth_headers,
        )
        assert res.status_code == 201, res.text
        project_id = res.json()["id"]
        assert res.json()["beta_features_enabled"] is False

        res = client.patch(
            f"/projects/{project_id}/settings",
            json={"interview_mode": "realtime_beta"},
            headers=auth_headers,
        )
        assert res.status_code == 403
        assert res.json()["detail"]["code"] == "beta_features_disabled"

        # Opt in, and the same patch is accepted.
        assert client.patch("/auth/me", json={"beta_features_enabled": True}, headers=auth_headers).status_code == 200
        res = client.patch(
            f"/projects/{project_id}/settings",
            json={"interview_mode": "realtime_beta"},
            headers=auth_headers,
        )
        assert res.status_code == 200
        assert res.json()["interview_mode"] == "realtime_beta"
        assert res.json()["beta_features_enabled"] is True

    def test_opt_in_defaults_off_and_round_trips_on_me(self, client, auth_headers):
        assert client.get("/auth/me", headers=auth_headers).json()["beta_features_enabled"] is False
        res = client.patch("/auth/me", json={"beta_features_enabled": True}, headers=auth_headers)
        assert res.status_code == 200
        assert res.json()["beta_features_enabled"] is True
        res = client.patch("/auth/me", json={"beta_features_enabled": False}, headers=auth_headers)
        assert res.json()["beta_features_enabled"] is False


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

        def fake_spawn(call_id, participant_id, total_minutes, segment_key=None):
            spawned.update(
                call_id=call_id, participant_id=participant_id,
                total=total_minutes, segment_key=segment_key,
            )

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
        # The recording segment for this connection reaches both the client
        # (upload tag) and the sideband (turn stamping).
        assert res.headers["x-realtime-segment"] == spawned["segment_key"]
        assert len(spawned["segment_key"]) == 32
        assert spawned["call_id"] == "rtc_test123"
        assert spawned["participant_id"] == participant.id
        assert spawned["total"] == 20

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

    def test_segments_record_side_by_side_without_deleting_each_other(self, client, db_session):
        """A resumed session (or second tab) is its own segment: uploading it
        must never overwrite or delete another connection's audio — the
        single-slot design once lost a morning recording to an afternoon
        resume, and a race left the DB pointing at a deleted file."""
        from app.models.interview import RealtimeRecordingSegment

        link, participant = _seed(db_session, "tok-seg")
        deleted = []
        urls = iter(["/audio/r/seg-a-1.mp3", "/audio/r/seg-b-1.mp3", "/audio/r/seg-a-2.mp3"])

        with patch("app.services.storage.upload_audio", side_effect=lambda *a, **k: next(urls)), \
             patch("app.services.storage.delete_audio_by_url", side_effect=deleted.append), \
             patch("app.services.transcode.needs_transcode", return_value=False):
            for seg in ("a" * 12, "b" * 12, "a" * 12):
                res = client.post(
                    f"/interview/{link.token}/{participant.id}/realtime/recording?segment={seg}",
                    files={"audio": ("session.webm", b"a" * 2048, "audio/webm")},
                )
                assert res.status_code == 200

        rows = (
            db_session.query(RealtimeRecordingSegment)
            .filter(RealtimeRecordingSegment.participant_id == participant.id)
            .all()
        )
        by_key = {r.segment_key: r.url for r in rows}
        # Segment a was replaced by its own re-upload; segment b untouched.
        assert by_key == {"a" * 12: "/audio/r/seg-a-2.mp3", "b" * 12: "/audio/r/seg-b-1.mp3"}
        assert deleted == ["/audio/r/seg-a-1.mp3"]

    def test_transcript_lists_recording_segments(self, client, db_session, auth_headers, registered_company):
        from app.models.company import Company
        from app.models.interview import RealtimeRecordingSegment

        link, participant = _seed(db_session, "tok-seg-list")
        db_session.add_all([
            RealtimeRecordingSegment(
                participant_id=participant.id, segment_key="k1", url="/audio/r/p1.mp3"
            ),
            RealtimeRecordingSegment(
                participant_id=participant.id, segment_key="k2", url="/audio/r/p2.mp3"
            ),
        ])
        turn = participant.turns[0]
        turn.audio_offset_seconds = 12.5
        turn.audio_segment_key = "k2"
        # Rehome the seeded project under the authed company so the
        # researcher transcript endpoint accepts it.
        company = db_session.query(Company).filter(Company.email == registered_company["email"]).first()
        participant.project.company_id = company.id
        db_session.commit()

        res = client.get(
            f"/projects/{participant.project_id}/participants/{participant.id}/transcript",
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert [s["segment_key"] for s in body["recording_segments"]] == ["k1", "k2"]
        assert body["turns"][0]["audio_segment_key"] == "k2"
        assert body["turns"][0]["audio_offset_seconds"] == 12.5

    def test_invalid_segment_key_is_rejected(self, client, db_session):
        link, participant = _seed(db_session, "tok-seg-bad")
        res = client.post(
            f"/interview/{link.token}/{participant.id}/realtime/recording?segment=../evil",
            files={"audio": ("session.webm", b"a" * 2048, "audio/webm")},
        )
        assert res.status_code == 422

    def test_gdpr_deletion_removes_segment_files(self, db_session):
        from app.models.interview import RealtimeRecordingSegment
        from app.services import deletion

        _, participant = _seed(db_session, "tok-seg-gdpr")
        participant.session_recording_url = "/audio/r/g1.mp3"
        db_session.add(
            RealtimeRecordingSegment(
                participant_id=participant.id, segment_key="g1", url="/audio/r/g1.mp3"
            )
        )
        db_session.add(
            RealtimeRecordingSegment(
                participant_id=participant.id, segment_key="g2", url="/audio/r/g2.mp3"
            )
        )
        db_session.commit()
        deleted = []
        with patch.object(deletion, "delete_audio_by_url", side_effect=lambda u: deleted.append(u) or True):
            deletion.delete_participant_data(db_session, participant)
        # Both segment files gone, the legacy pointer deduped (same file).
        assert sorted(deleted) == ["/audio/r/g1.mp3", "/audio/r/g2.mp3"]
        assert (
            db_session.query(RealtimeRecordingSegment)
            .filter(RealtimeRecordingSegment.participant_id == participant.id)
            .count()
            == 0
        )

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

    def test_hesitation_fragments_are_not_answers(self):
        """VAD commits "So" / "Ah." while the participant lines up a thought;
        treating those as answers makes Claude probe mid-thought."""
        assert rt._is_hesitation_only("So", "en") is True
        assert rt._is_hesitation_only("Ah.", "en") is True
        assert rt._is_hesitation_only("Okay, so, um...", "en") is True
        # The spoken acknowledgment's echo, should it ever reach the mic.
        assert rt._is_hesitation_only("Gotcha.", "en") is True
        assert rt._is_hesitation_only("Euh... alors...", "fr") is True
        assert rt._is_hesitation_only("D'accord.", "fr") is True
        assert rt._is_hesitation_only("", "en") is True
        # Real short answers keep flowing.
        assert rt._is_hesitation_only("No", "en") is False
        assert rt._is_hesitation_only("Netflix mostly", "en") is False
        assert rt._is_hesitation_only("Oui", "fr") is False
        assert rt._is_hesitation_only("So basically the billing broke", "en") is False

    def test_hesitation_fragment_holds_the_turn_open(self, db_session, bridge_sessions, monkeypatch):
        monkeypatch.setattr(rt, "ANSWER_DRAIN_SECONDS", 0.05)
        _, participant = _seed(db_session, "tok-hesit", turns=1)
        pending_before = rt._pending_question(participant.id)
        bridge = rt.SidebandBridge("rtc_hesit", participant.id, 20)
        ws = _FakeWs()
        bridge._handle_transcript(
            ws,
            {"type": "conversation.item.input_audio_transcription.completed", "transcript": "So"},
        )
        # No ack, no next question, no "could you repeat": total silence,
        # the turn stays open for the real answer.
        assert ws.sent == []
        assert rt._pending_question(participant.id) == pending_before

    def test_short_answer_waits_for_the_rest_of_the_sentence(self, db_session, bridge_sessions, monkeypatch):
        monkeypatch.setattr(rt, "ANSWER_DRAIN_SECONDS", 0.05)
        monkeypatch.setattr(rt, "SHORT_ANSWER_EXTRA_WAIT", 0.6)
        _, participant = _seed(db_session, "tok-short2", turns=1)
        bridge = rt.SidebandBridge("rtc_short2", participant.id, 20)
        continuation = {
            "type": "conversation.item.input_audio_transcription.completed",
            "transcript": "and Disney for the kids",
        }
        # The continuation only arrives after the normal drain window: a
        # fixed 1s drain would have answered "Netflix mostly" on its own.
        ws = _FakeWs(events=[continuation], delay_calls=15)
        combined = bridge._collect_answer(ws, "Netflix mostly")
        assert combined == "Netflix mostly and Disney for the kids"

    def test_barge_in_is_off_so_the_interviewer_cannot_cut_itself_off(self, db_session):
        _, participant = _seed(db_session, "tok-barge")
        cfg = rt.build_session_config(participant.project, participant, "fr")
        assert cfg["audio"]["input"]["turn_detection"]["interrupt_response"] is False

    def test_turn_offsets_are_stamped_into_the_recording_timeline(self, db_session, bridge_sessions):
        _, participant = _seed(db_session, "tok-offset", turns=2)
        rt._stamp_turn_offset(participant.id, 1, 42.37)
        db_session.expire_all()
        turns = {t.turn_index: t for t in participant.turns}
        assert turns[1].audio_offset_seconds == 42.4
        assert turns[0].audio_offset_seconds is None
        # First write wins — a reconnect must not rewrite history against a
        # recording that no longer matches.
        rt._stamp_turn_offset(participant.id, 1, 99.9)
        db_session.expire_all()
        assert {t.turn_index: t for t in participant.turns}[1].audio_offset_seconds == 42.4

    def test_recording_upload_survives_gate_flips_mid_session(self, client, db_session):
        """Leaving the beta (or the kill switch) stops NEW sessions, never
        the audio of one already running."""
        link, participant = _seed(db_session, "tok-rec-flip", beta=False)
        with patch.object(settings, "REALTIME_INTERVIEW_ENABLED", False), \
             patch("app.services.storage.upload_audio", return_value="/audio/recordings/x/s.mp3"), \
             patch("app.services.transcode.needs_transcode", return_value=False):
            res = client.post(
                f"/interview/{link.token}/{participant.id}/realtime/recording",
                files={"audio": ("session.webm", b"a" * 2048, "audio/webm")},
            )
        assert res.status_code == 200

        # But a plain classic study with no recording still has no endpoint.
        link2, p2 = _seed(db_session, "tok-rec-classic2", mode="classic")
        res = client.post(
            f"/interview/{link2.token}/{p2.id}/realtime/recording",
            files={"audio": ("session.webm", b"a" * 2048, "audio/webm")},
        )
        assert res.status_code == 404

    def test_transcript_payload_carries_turn_offsets(self, client, db_session, auth_headers, registered_company):
        from app.models.company import Company as _C
        link, participant = _seed(db_session, "tok-offset-api", turns=2)
        # Re-home the seeded project under the authenticated company so the
        # researcher transcript endpoint can read it.
        me = db_session.query(_C).filter(_C.email == "test@example.com").first()
        participant.project.company_id = me.id
        turns = sorted(participant.turns, key=lambda t: t.turn_index)
        turns[0].audio_offset_seconds = 3.2
        db_session.commit()

        res = client.get(
            f"/projects/{participant.project_id}/participants/{participant.id}/transcript",
            headers=auth_headers,
        )
        assert res.status_code == 200, res.text
        got = {t["turn_index"]: t.get("audio_offset_seconds") for t in res.json()["turns"]}
        assert got[0] == 3.2
        assert got[1] is None

    def test_session_config_carries_language_and_vad(self, db_session):
        _, participant = _seed(db_session, "tok-config")
        cfg = rt.build_session_config(participant.project, participant, "fr")
        assert cfg["audio"]["input"]["transcription"]["language"] == "fr"
        assert cfg["audio"]["input"]["turn_detection"]["create_response"] is False
        # Noise reduction runs before VAD, so room noise and speaker bleed
        # are filtered before they can commit as participant speech.
        assert cfg["audio"]["input"]["noise_reduction"] == {"type": "far_field"}
        assert "verbatim" in cfg["instructions"].lower() or "exact" in cfg["instructions"].lower()
        assert json.dumps(cfg)  # serialisable
