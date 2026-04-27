"""Tests for Level-1 (Claude streaming) + Level-2 (TTS streaming) interview pipeline.

These verify:
- The /audio/stream/{turn_id} endpoint streams TTS bytes via chunked transfer.
- decide_next_action uses the Anthropic streaming API (messages.stream), not the
  blocking messages.create.
- process_interview_turn returns a /audio/stream/... URL instead of an R2 URL.
- The streaming endpoint persists audio to R2 in a background task once the
  stream completes, so future replays don't re-stream from OpenAI.
- Client aborts mid-stream do NOT trigger a partial upload.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.company import Company
from app.models.interview import InterviewLink, InterviewTurn, Participant
from app.models.project import InterviewGuideQuestion, Project
from app.services import interview_engine as ie


# ─── Shared fixtures ─────────────────────────────────────────────────────────


def _make_minimal_setup(db):
    company = Company(name="T", email="t2@test.com", password_hash="x")
    db.add(company)
    db.commit()
    db.refresh(company)

    project = Project(
        company_id=company.id, name="P", language="en", interview_duration_minutes=20,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    db.add(InterviewGuideQuestion(
        project_id=project.id, section_index=0, section_title="S",
        question_index=0, main_question="Q0", desired_learning="learn", sort_order=0,
    ))
    db.commit()

    link = InterviewLink(project_id=project.id, token="tok-stream", is_active=True)
    db.add(link)
    db.commit()
    db.refresh(link)

    participant = Participant(
        link_id=link.id, project_id=project.id, display_name="P",
        status="in_progress", started_at=datetime.utcnow() - timedelta(minutes=1),
        talk_seconds=0.0,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)

    turn = InterviewTurn(
        participant_id=participant.id, turn_index=0, question_index=0,
        question_text="Hello, please tell me about yourself",
        is_follow_up=False, follow_up_index=0, turn_kind="main",
    )
    db.add(turn)
    db.commit()
    db.refresh(turn)

    return company, project, link, participant, turn


def _claude_stream_message(payload: dict):
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(payload))]
    msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    msg.model = "claude-sonnet-4-20250514"
    msg.stop_reason = "end_turn"
    return msg


def _wire_stream(client, *messages):
    msgs = [_claude_stream_message(m) if isinstance(m, dict) else m for m in messages]

    def stream_factory(*args, **kwargs):
        ctx = MagicMock()
        if msgs:
            final = msgs.pop(0)
        else:
            final = _claude_stream_message({"action": "next_question", "question": "next"})
        ctx.__enter__.return_value.get_final_message.return_value = final
        ctx.__exit__.return_value = False
        return ctx

    client.messages.stream.side_effect = stream_factory
    return client


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestAudioStreamEndpoint:
    def test_stream_endpoint_returns_chunked_audio(self, client, db_session):
        """GET /audio/stream/{turn_id} returns audio/mpeg with concatenated chunks."""
        _, _, _, _, turn = _make_minimal_setup(db_session)
        chunks = [b"\x01\x02", b"\x03\x04", b"\x05"]
        with patch(
            "app.routers.audio.generate_speech_streaming",
            return_value=iter(chunks),
        ), patch("app.routers.audio.threading.Thread"):  # don't actually upload
            resp = client.get(f"/audio/stream/{turn.id}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/mpeg")
        assert resp.headers.get("cache-control") == "no-store"
        assert resp.content == b"".join(chunks)

    def test_stream_endpoint_404_on_missing_turn(self, client):
        resp = client.get("/audio/stream/does-not-exist")
        assert resp.status_code == 404

    def test_stream_endpoint_404_on_empty_question_text(self, client, db_session):
        _, _, _, participant, _ = _make_minimal_setup(db_session)
        empty_turn = InterviewTurn(
            participant_id=participant.id, turn_index=99, question_index=0,
            question_text="", is_follow_up=False, follow_up_index=0, turn_kind="main",
        )
        db_session.add(empty_turn)
        db_session.commit()
        db_session.refresh(empty_turn)
        resp = client.get(f"/audio/stream/{empty_turn.id}")
        assert resp.status_code == 404

    def test_background_upload_persists_to_r2(self, client, db_session, engine):
        """After the stream completes, turn.tts_audio_url should be replaced with
        the persisted (non-stream) URL via upload_audio."""
        from sqlalchemy.orm import sessionmaker
        _, _, _, _, turn = _make_minimal_setup(db_session)
        chunks = [b"\x01" * 10, b"\x02" * 10]

        # Capture the background thread so we can join on it.
        threads: list[threading.Thread] = []
        real_thread = threading.Thread

        def thread_factory(target, args=(), daemon=True, **kw):
            t = real_thread(target=target, args=args, daemon=daemon, **kw)
            threads.append(t)
            return t

        # Bind the background-task SessionLocal to the same in-memory test engine.
        TestSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

        with patch(
            "app.routers.audio.generate_speech_streaming",
            return_value=iter(chunks),
        ), patch(
            "app.routers.audio.upload_audio",
            return_value="https://r2.example.com/tts/abc.mp3",
        ) as up, patch(
            "app.routers.audio.threading.Thread", side_effect=thread_factory,
        ), patch("app.routers.audio.SessionLocal", TestSessionLocal):
            resp = client.get(f"/audio/stream/{turn.id}")
            assert resp.status_code == 200
            _ = resp.content

        for t in threads:
            t.join(timeout=3.0)

        up.assert_called_once()
        called_bytes, called_key = up.call_args.args
        assert called_bytes == b"".join(chunks)
        assert called_key.startswith("tts/")

        db_session.expire_all()
        refreshed = db_session.query(InterviewTurn).filter(InterviewTurn.id == turn.id).first()
        assert refreshed.tts_audio_url == "https://r2.example.com/tts/abc.mp3"

    def test_client_abort_does_not_persist_partial(self, client, db_session):
        """If the streaming generator raises mid-stream, no R2 upload happens."""
        _, _, _, _, turn = _make_minimal_setup(db_session)

        def bad_gen():
            yield b"partial"
            raise RuntimeError("openai blew up")

        threads: list[threading.Thread] = []
        real_thread = threading.Thread

        def thread_factory(target, args=(), daemon=True, **kw):
            t = real_thread(target=target, args=args, daemon=daemon, **kw)
            threads.append(t)
            return t

        with patch(
            "app.routers.audio.generate_speech_streaming",
            side_effect=lambda text: bad_gen(),
        ), patch("app.routers.audio.upload_audio") as up, \
             patch("app.routers.audio.threading.Thread", side_effect=thread_factory):
            try:
                resp = client.get(f"/audio/stream/{turn.id}")
                _ = resp.content
            except Exception:
                # TestClient may surface the generator error — that's fine.
                pass

        for t in threads:
            t.join(timeout=2.0)

        # No partial bytes were uploaded
        up.assert_not_called()


# ─── Claude streaming wiring ─────────────────────────────────────────────────


class TestClaudeStreaming:
    def test_decide_next_action_uses_streaming(self, db_session):
        """Verify decide_next_action calls messages.stream(), not messages.create()."""
        _, project, link, participant, _ = _make_minimal_setup(db_session)

        with patch("app.services.interview_engine.anthropic.Anthropic") as anth:
            cli = MagicMock()
            _wire_stream(cli, {"action": "next_question", "question": "Next thing"})
            anth.return_value = cli

            decision = ie.decide_next_action(
                system_prompt="",
                interview_guide_str="<g>",
                conversation_history="P: hi\n",
                current_question_index=0,
                elapsed_minutes=2.0,
                total_minutes=10,
                all_questions_done=False,
                total_questions=2,
                talk_minutes=1.5,
                interview_plan=None,
                fatigue_state=None,
                turns=[],
            )

        assert cli.messages.stream.called
        assert not cli.messages.create.called
        assert decision["action"] == "next_question"
        assert decision["question"] == "Next thing"

    def test_process_turn_returns_streaming_url(self, db_session):
        """process_interview_turn should return tts_audio_url = /audio/stream/{turn_id}."""
        _, project, link, participant, _ = _make_minimal_setup(db_session)

        with patch(
            "app.services.interview_engine.transcribe_audio",
            return_value=("a real answer with several words here ok", 6.0),
        ), patch(
            "app.services.interview_engine.download_audio", return_value=b""
        ), patch(
            "app.services.interview_engine.anthropic.Anthropic"
        ) as anth:
            cli = MagicMock()
            _wire_stream(cli, {"action": "next_question", "question": "Next Q"})
            anth.return_value = cli

            result = ie.process_interview_turn(participant.id, "fake.webm", db_session)

        assert result["tts_audio_url"].startswith("/audio/stream/")
        # The DB row should have the same URL
        last = db_session.query(InterviewTurn).filter(
            InterviewTurn.participant_id == participant.id,
        ).order_by(InterviewTurn.turn_index.desc()).first()
        assert last.tts_audio_url == result["tts_audio_url"]
        assert result["tts_audio_url"].endswith(last.id)

    def test_start_interview_returns_streaming_url(self, db_session):
        """start_interview should also use the streaming-URL pattern."""
        _, project, link, _, _ = _make_minimal_setup(db_session)
        # Drop the seeded turn so start_interview creates a fresh one
        db_session.query(InterviewTurn).delete()
        db_session.commit()

        # Create a brand-new participant with no turns.
        p2 = Participant(
            link_id=link.id, project_id=project.id, display_name="P2",
            status="in_progress", started_at=datetime.utcnow(), talk_seconds=0.0,
        )
        db_session.add(p2)
        db_session.commit()
        db_session.refresh(p2)

        # No ANTHROPIC_API_KEY → falls back without calling Claude.
        result = ie.start_interview(p2.id, db_session)
        assert result["tts_audio_url"].startswith("/audio/stream/")
