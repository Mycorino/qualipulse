"""Realtime interview beta — OpenAI Realtime API transport, Claude brain.

The participant's browser talks WebRTC directly to the OpenAI Realtime API
(`gpt-realtime` listens, detects turns, and speaks), while this module keeps
the interview logic exactly where it already lives: the backend proxies the
SDP exchange (so the standard API key never reaches the client and we get the
call id server-side), then attaches a **sideband** WebSocket to the same call
(`wss://api.openai.com/v1/realtime?call_id=...`). On every completed user
turn transcription the sideband feeds the transcript into
``process_interview_turn(transcript_override=...)`` — the same code path as
the typed-answer fallback — so pacing guards, follow-up caps, the close gate,
the final check, completion, credits and all completion side effects behave
identically to classic interviews. The realtime model is only the mouth: it
is instructed to speak the host-provided line verbatim and never invent
content (``create_response: false`` on VAD, belt and braces).

Audio: the Realtime API neither returns nor stores raw audio, so the browser
records the whole session in parallel (mic + assistant voice mixed) and
uploads it at the end — see the /realtime/recording endpoint. Turn rows
therefore carry transcripts but no per-turn ``audio_recording_url``.

Sync + daemon-thread by design, matching the rest of the backend (analysis,
translation, cleanup all run this way on Cloud Run with CPU always on).
"""

import json
import logging
import re
import threading
import time
import uuid

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"
REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"

# Floor for the session watchdog: even a "5 minute" study gets this long
# before the sideband hangs up, so setup fumbling never kills a real session.
MIN_SESSION_MINUTES = 20.0

# How long after a VAD-committed transcript we keep listening for the
# participant to resume before treating the answer as finished. With
# semantic_vad the model already waits out unfinished sentences, so this is
# only a short net for back-to-back commits; every extra tenth of a second
# here is dead air the participant sits through on EVERY turn.
ANSWER_DRAIN_SECONDS = 1.0
# If speech restarts inside the drain window, wait at most this long for its
# transcription before advancing with what we have.
ANSWER_CONTINUATION_TIMEOUT = 20.0

# Speaker-to-mic echo: for this long after the interviewer stops speaking, a
# transcript that echoes what it just said is treated as the room hearing the
# interviewer, not the participant answering.
ECHO_TAIL_SECONDS = 2.0
# Word overlap with the just-spoken line above which a transcript is echo.
ECHO_OVERLAP_RATIO = 0.6
# How long a queued line waits for the in-flight response to finish before
# giving up and sending anyway.
RESPONSE_IDLE_TIMEOUT = 20.0

# Estimated per-token USD rates for gpt-realtime (audio/text, cached input
# discounted). Estimates for the admin cost dashboards and the daily
# interview spend ceiling — the invoice truth lives with OpenAI.
_REALTIME_RATES = {
    "audio_in": 32.0 / 1_000_000,
    "audio_in_cached": 0.40 / 1_000_000,
    "text_in": 4.0 / 1_000_000,
    "text_in_cached": 0.40 / 1_000_000,
    "audio_out": 64.0 / 1_000_000,
    "text_out": 16.0 / 1_000_000,
}


class RealtimeCallError(RuntimeError):
    """The OpenAI Realtime call could not be created."""


def _session_instructions(language: str | None) -> str:
    lang = language or "en"
    return (
        "You are the live voice of a professional research interviewer. "
        "A host system decides every question and hands you the exact line to "
        "say through response instructions. Speak ONLY those lines, verbatim, "
        "warmly and naturally, then stop and wait. Never add your own "
        "questions, commentary, reactions, or filler; never answer the "
        "participant's questions yourself; never switch language. "
        f"The interview language is: {lang}. "
        "Never use em dashes in anything you say."
    )


def build_session_config(project, participant, language: str | None) -> dict:
    """Realtime session config sent with the SDP exchange.

    ``create_response: false`` is the load-bearing bit: VAD still commits the
    participant's audio and triggers transcription, but the model stays
    silent until the sideband has run the Claude decision and asks for the
    next line via ``response.create``.
    """
    transcription: dict = {"model": settings.REALTIME_TRANSCRIBE_MODEL}
    lang2 = (language or "")[:2]
    if lang2:
        transcription["language"] = lang2
    if settings.REALTIME_VAD_TYPE == "server_vad":
        turn_detection = {
            "type": "server_vad",
            "create_response": False,
            "interrupt_response": settings.REALTIME_ALLOW_BARGE_IN,
            "silence_duration_ms": settings.REALTIME_VAD_SILENCE_MS,
        }
    else:
        # semantic_vad holds the turn open while a sentence sounds
        # unfinished; low eagerness biases further toward letting the
        # participant think out loud without being cut off.
        turn_detection = {
            "type": "semantic_vad",
            "eagerness": settings.REALTIME_VAD_EAGERNESS,
            "create_response": False,
            "interrupt_response": settings.REALTIME_ALLOW_BARGE_IN,
        }
    return {
        "type": "realtime",
        "model": settings.REALTIME_MODEL,
        "instructions": _session_instructions(language),
        "audio": {
            "input": {
                "transcription": transcription,
                "turn_detection": turn_detection,
            },
            "output": {"voice": settings.REALTIME_VOICE},
        },
    }


def create_realtime_call(sdp_offer: str, session_config: dict) -> tuple[str, str]:
    """Proxy the browser's SDP offer to OpenAI; return (answer_sdp, call_id).

    Uses the unified interface: multipart form with the offer and the session
    config, authenticated with the standard API key. The call id comes back
    in the Location header and is what the sideband attaches to.
    """
    if not settings.OPENAI_API_KEY:
        raise RealtimeCallError("OPENAI_API_KEY is not configured")
    try:
        resp = httpx.post(
            REALTIME_CALLS_URL,
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            files={
                "sdp": (None, sdp_offer, "application/sdp"),
                "session": (None, json.dumps(session_config), "application/json"),
            },
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise RealtimeCallError(f"Realtime call creation failed: {exc}") from exc
    if resp.status_code >= 400:
        raise RealtimeCallError(
            f"Realtime call creation failed: HTTP {resp.status_code} {resp.text[:500]}"
        )
    location = resp.headers.get("Location") or resp.headers.get("location") or ""
    call_id = location.rstrip("/").rsplit("/", 1)[-1] if location else ""
    if not call_id:
        raise RealtimeCallError("Realtime call created but no call id in Location header")
    return resp.text, call_id


def _log_realtime_usage(participant_id: str, usage: dict) -> None:
    """One AIUsageLog row per model response. Best-effort, own session.

    Counting realtime spend here keeps the per-workspace daily interview
    ceiling (_check_interview_budget) effective for realtime interviews too.
    """
    try:
        from app.database import session_scope
        from app.models.interview import Participant
        from app.models.usage import AIUsageLog

        in_details = usage.get("input_token_details") or {}
        out_details = usage.get("output_token_details") or {}
        cached = in_details.get("cached_tokens_details") or {}
        cached_audio = cached.get("audio_tokens", 0) or 0
        cached_text = cached.get("text_tokens", 0) or 0
        audio_in = max(0, (in_details.get("audio_tokens", 0) or 0) - cached_audio)
        text_in = max(0, (in_details.get("text_tokens", 0) or 0) - cached_text)
        cost = (
            audio_in * _REALTIME_RATES["audio_in"]
            + cached_audio * _REALTIME_RATES["audio_in_cached"]
            + text_in * _REALTIME_RATES["text_in"]
            + cached_text * _REALTIME_RATES["text_in_cached"]
            + (out_details.get("audio_tokens", 0) or 0) * _REALTIME_RATES["audio_out"]
            + (out_details.get("text_tokens", 0) or 0) * _REALTIME_RATES["text_out"]
        )
        with session_scope() as db:
            participant = db.query(Participant).filter(Participant.id == participant_id).first()
            if participant is None:
                return
            db.add(
                AIUsageLog(
                    company_id=participant.project.company_id if participant.project else None,
                    project_id=participant.project_id,
                    participant_id=participant_id,
                    operation="realtime_interview",
                    model=settings.REALTIME_MODEL,
                    input_tokens=usage.get("input_tokens", 0) or 0,
                    output_tokens=usage.get("output_tokens", 0) or 0,
                    cost_usd=round(cost, 6),
                )
            )
            db.commit()
    except Exception:
        logger.exception("realtime usage logging failed for participant %s", participant_id)


def _last_turn_index(participant_id: str) -> int | None:
    from app.database import session_scope
    from app.models.interview import Participant

    with session_scope() as db:
        participant = db.query(Participant).filter(Participant.id == participant_id).first()
        if participant is None or not participant.turns:
            return None
        return max(t.turn_index for t in participant.turns)


def _pending_question(participant_id: str) -> str | None:
    """The question the participant has not answered yet (supports resume)."""
    from app.database import session_scope
    from app.models.interview import Participant

    with session_scope() as db:
        participant = db.query(Participant).filter(Participant.id == participant_id).first()
        if participant is None or participant.status == "completed":
            return None
        turns = sorted(participant.turns, key=lambda t: t.turn_index)
        if not turns:
            return None
        last = turns[-1]
        if last.response_transcript:
            return None
        return last.question_text


_ACK_EXAMPLES = {
    "en": "'Okay.', 'I see.', 'Got it.'",
    "fr": "'D'accord.', 'Je vois.', 'Très bien.'",
    "de": "'Okay.', 'Verstehe.', 'Alles klar.'",
    "es": "'Vale.', 'Entiendo.', 'Muy bien.'",
    "it": "'Va bene.', 'Capisco.', 'Certo.'",
    "pt": "'Certo.', 'Entendo.', 'Muito bem.'",
}


def _ack_instruction(language: str | None) -> str:
    lang = (language or "en")[:2]
    examples = _ACK_EXAMPLES.get(lang, _ACK_EXAMPLES["en"])
    return (
        f"Say ONE very brief, natural acknowledgment in the interview language "
        f"({lang}), one to three words, in a warm listening tone, for example "
        f"{examples} Vary it. Say nothing else and ask nothing."
    )


def _normalise_for_echo(text: str) -> list[str]:
    return [w for w in re.sub(r"[^\w\s]", " ", (text or "").lower()).split() if len(w) > 2]


def _looks_like_echo(transcript: str, spoken: str) -> bool:
    """True when a transcript is mostly the interviewer's own last line.

    Speakers leak into the microphone, so the interviewer's question can come
    back as if the participant had said it. Feeding that to Claude produces an
    interview where the AI answers itself, so drop it. Compared on content
    words only, and only ever consulted while (or just after) the interviewer
    was actually speaking, so a genuine short answer is never discarded.
    """
    said = _normalise_for_echo(transcript)
    mine = set(_normalise_for_echo(spoken))
    if not said or not mine:
        return False
    overlap = sum(1 for w in said if w in mine)
    return overlap / len(said) >= ECHO_OVERLAP_RATIO


def _repeat_line(language: str | None) -> str:
    lang = (language or "en")[:2]
    lines = {
        "en": "Sorry, I couldn't quite catch that. Could you say it again?",
        "fr": "Pardon, je n'ai pas bien entendu. Pouvez-vous répéter ?",
        "de": "Entschuldigung, das habe ich nicht ganz verstanden. Können Sie das noch einmal sagen?",
        "es": "Perdón, no le he entendido bien. ¿Puede repetirlo?",
        "it": "Scusi, non ho capito bene. Può ripetere?",
        "pt": "Desculpe, não percebi bem. Pode repetir?",
    }
    return lines.get(lang, lines["en"])


def _interview_language(participant_id: str) -> str:
    from app.database import session_scope
    from app.models.interview import Participant

    with session_scope() as db:
        p = db.query(Participant).filter(Participant.id == participant_id).first()
        if p is None:
            return "en"
        return (
            getattr(p, "preferred_language", None)
            or (p.project.language if p.project else None)
            or "en"
        )


def _stamp_turn_offset(participant_id: str, turn_index: int | None, seconds: float) -> None:
    """Record where a turn's question starts inside the session recording.

    The recording starts when the browser receives the remote audio track,
    within a second or two of the sideband attaching, so seconds-since-
    attach lands the player just before the question. Best-effort.
    """
    if turn_index is None:
        return
    try:
        from app.database import session_scope
        from app.models.interview import InterviewTurn

        with session_scope() as db:
            turn = (
                db.query(InterviewTurn)
                .filter(
                    InterviewTurn.participant_id == participant_id,
                    InterviewTurn.turn_index == turn_index,
                )
                .first()
            )
            if turn is not None and turn.audio_offset_seconds is None:
                turn.audio_offset_seconds = round(max(0.0, seconds), 1)
                db.commit()
    except Exception:
        logger.exception("could not stamp audio offset for participant %s", participant_id)


def _advance_turn(participant_id: str, transcript: str) -> dict | None:
    """Run one interview turn on the shared engine. Returns the engine result,
    or None when the transcript was rejected as silence/noise."""
    from app.database import session_scope
    from app.services.interview_engine import EmptyTranscriptError, process_interview_turn

    try:
        with session_scope() as db:
            return process_interview_turn(
                participant_id,
                audio_path=None,
                audio_url=None,
                db=db,
                transcript_override=transcript,
            )
    except EmptyTranscriptError:
        return None


class SidebandBridge:
    """One realtime call's server-side driver.

    Owns the sideband WebSocket, replays queued events, and turns each
    completed input transcription into a Claude-decided next line.
    """

    def __init__(self, call_id: str, participant_id: str, total_minutes: int | None):
        self.call_id = call_id
        self.participant_id = participant_id
        budget = max(MIN_SESSION_MINUTES, (total_minutes or 0) * settings.REALTIME_MAX_SESSION_FACTOR)
        self.deadline = time.monotonic() + budget * 60
        self.language = _interview_language(participant_id)
        self.closing = False
        # Half-duplex bookkeeping: what the interviewer is saying right now
        # (so its echo can be recognised) and whether a response is in
        # flight (so two lines never race for the same audio channel).
        self.response_active = False
        self.last_spoken = ""
        self.last_response_ended_at = 0.0
        # Set when the sideband attaches — the zero point for per-turn
        # offsets into the client's session recording.
        self.session_started_at: float | None = None

    # -- websocket plumbing -------------------------------------------------

    def _connect(self):
        from websockets.sync.client import connect

        url = f"{REALTIME_WS_URL}?call_id={self.call_id}"
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        try:
            return connect(url, additional_headers=headers, open_timeout=15)
        except TypeError:  # older websockets releases use extra_headers
            return connect(url, extra_headers=headers, open_timeout=15)

    def _send(self, ws, payload: dict) -> None:
        ws.send(json.dumps(payload))

    def _session_elapsed(self) -> float:
        if self.session_started_at is None:
            return 0.0
        return time.monotonic() - self.session_started_at

    def _speak(self, ws, text: str) -> None:
        """Queue one spoken line, after whatever is playing has finished.

        Two overlapping ``response.create`` calls (the acknowledgment and the
        question that follows it) leave the model with two lines for one
        audio channel, which it resolves by cutting the first one off
        mid-sentence. Waiting for the channel keeps them sequential.
        """
        self._wait_for_response_idle(ws)
        self.last_spoken = text
        self._send(
            ws,
            {
                "type": "response.create",
                "response": {
                    "instructions": (
                        "Say exactly the following line to the participant, "
                        "verbatim, warmly and naturally. Do not add, remove, "
                        "or change anything:\n" + text
                    ),
                },
            },
        )

    def _wait_for_response_idle(self, ws) -> None:
        """Pump events until nothing is being spoken (bounded)."""
        deadline = min(time.monotonic() + RESPONSE_IDLE_TIMEOUT, self.deadline)
        while self.response_active and time.monotonic() < deadline:
            event = self._recv_event(ws, timeout=0.25)
            if event is not None:
                self._note_event(event)

    def _note_event(self, event: dict) -> str:
        """Update speaking state from any event; returns its type."""
        etype = event.get("type", "")
        if etype == "response.created":
            self.response_active = True
        elif etype == "response.done":
            self.response_active = False
            self.last_response_ended_at = time.monotonic()
            self._on_response_done(event)
        elif etype == "error":
            logger.warning(
                "realtime event error for participant %s: %s",
                self.participant_id, json.dumps(event)[:500],
            )
        return etype

    def _is_echo(self, transcript: str) -> bool:
        """Was this the interviewer's own voice coming back through the mic?"""
        speaking_recently = (
            self.response_active
            or (time.monotonic() - self.last_response_ended_at) < ECHO_TAIL_SECONDS
        )
        return speaking_recently and _looks_like_echo(transcript, self.last_spoken)

    def _recv_event(self, ws, timeout: float) -> dict | None:
        try:
            raw = ws.recv(timeout=timeout)
        except TimeoutError:
            return None
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return event if isinstance(event, dict) else None

    # -- event handling -----------------------------------------------------

    @staticmethod
    def _is_transcript_done(event: dict) -> bool:
        return event.get("type", "").endswith("input_audio_transcription.completed")

    def _collect_answer(self, ws, first: str) -> str:
        """Concatenate transcripts until the participant stays quiet.

        VAD commits on short pauses, so one spoken answer can arrive as two
        or three transcription events. Keep draining briefly after each one;
        if speech restarts inside the window, wait for its transcription.
        """
        parts = [first]
        wait_until = time.monotonic() + ANSWER_DRAIN_SECONDS
        while time.monotonic() < min(wait_until, self.deadline):
            event = self._recv_event(ws, timeout=0.25)
            if event is None:
                continue
            etype = self._note_event(event)
            if etype == "input_audio_buffer.speech_started":
                wait_until = time.monotonic() + ANSWER_CONTINUATION_TIMEOUT
            elif self._is_transcript_done(event):
                text = (event.get("transcript") or "").strip()
                if text and not self._is_echo(text):
                    parts.append(text)
                wait_until = time.monotonic() + ANSWER_DRAIN_SECONDS
        return " ".join(p for p in parts if p)

    def _on_response_done(self, event: dict) -> None:
        usage = (event.get("response") or {}).get("usage")
        if usage:
            _log_realtime_usage(self.participant_id, usage)
        if self.closing:
            # The wrap-up line has been fully spoken: the call is over.
            raise _SessionDone()

    def _handle_transcript(self, ws, event: dict) -> None:
        transcript = (event.get("transcript") or "").strip()
        if transcript and self._is_echo(transcript):
            # The interviewer hearing itself. Not an answer: say nothing,
            # ask nothing, and leave the turn open for the participant.
            logger.info(
                "realtime: dropped echo of the interviewer's own line (participant=%s)",
                self.participant_id,
            )
            return
        transcript = self._collect_answer(ws, transcript) if transcript else ""
        if not transcript:
            self._speak(ws, _repeat_line(self.language))
            return
        if settings.REALTIME_ACK_ENABLED:
            # Fill the Claude-decision gap with a human "I heard you" beat
            # instead of silence. _speak below waits for this to finish, so
            # the question never talks over the acknowledgment.
            self.response_active = True
            self.last_spoken = ""
            self._send(
                ws,
                {"type": "response.create", "response": {"instructions": _ack_instruction(self.language)}},
            )
        result = _advance_turn(self.participant_id, transcript)
        if result is None:
            self._speak(ws, _repeat_line(self.language))
            return
        if result.get("is_complete"):
            self.closing = True
        self._speak(ws, result["question_text"])
        _stamp_turn_offset(self.participant_id, result.get("turn_index"), self._session_elapsed())

    # -- main loop ----------------------------------------------------------

    def run(self) -> None:
        try:
            with self._connect() as ws:
                logger.info(
                    "realtime sideband attached call=%s participant=%s",
                    self.call_id, self.participant_id,
                )
                self.session_started_at = time.monotonic()
                opening = _pending_question(self.participant_id)
                if opening:
                    self._speak(ws, opening)
                    _stamp_turn_offset(
                        self.participant_id, _last_turn_index(self.participant_id), self._session_elapsed()
                    )
                while time.monotonic() < self.deadline:
                    event = self._recv_event(ws, timeout=30.0)
                    if event is None:
                        continue
                    etype = self._note_event(event)
                    if self._is_transcript_done(event):
                        self._handle_transcript(ws, event)
                    elif etype.endswith("input_audio_transcription.failed"):
                        self._speak(ws, _repeat_line(self.language))
                else:
                    logger.warning(
                        "realtime session deadline reached for participant %s; hanging up",
                        self.participant_id,
                    )
        except _SessionDone:
            logger.info(
                "realtime interview completed call=%s participant=%s",
                self.call_id, self.participant_id,
            )
        except Exception:
            # The participant's client sees the call drop and falls back to
            # its error state; the interview itself resumes like any other
            # in-progress interview.
            logger.exception(
                "realtime sideband crashed call=%s participant=%s",
                self.call_id, self.participant_id,
            )


class _SessionDone(Exception):
    """Internal: the closing line finished playing; hang up cleanly."""


def spawn_sideband(call_id: str, participant_id: str, total_minutes: int | None) -> None:
    bridge = SidebandBridge(call_id, participant_id, total_minutes)
    threading.Thread(
        target=bridge.run, daemon=True, name=f"realtime-{participant_id[:8]}"
    ).start()


def store_session_recording(participant, data: bytes, ext: str, db) -> str:
    """Transcode (if needed) and store the browser's full-session capture.

    The client uploads incrementally (every ~45s and on tab hide), so this
    runs repeatedly per interview: each upload gets a fresh key (no stale
    browser/CDN caching of a shorter file) and the superseded file is
    deleted afterwards, so exactly one recording remains referenced and on
    disk — the GDPR cascade only knows about the referenced URL.
    """
    from app.services.storage import delete_audio_by_url, upload_audio
    from app.services.transcode import needs_transcode, transcode_to_mp3

    if needs_transcode(ext):
        converted = transcode_to_mp3(data, ext)
        if converted is not None:
            data, ext = converted, ".mp3"
    key = f"recordings/{participant.id}/session-{uuid.uuid4().hex}{ext}"
    url = upload_audio(data, key)
    previous = participant.session_recording_url
    participant.session_recording_url = url
    db.commit()
    if previous and previous != url:
        try:
            delete_audio_by_url(previous)
        except Exception:
            logger.warning("could not delete superseded session recording %s", previous)
    return url
