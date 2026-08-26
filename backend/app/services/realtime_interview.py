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
# participant to resume before treating the answer as finished. Realtime VAD
# commits on ~0.5-1s pauses; a thinking pause mid-answer is longer than that
# but shorter than this.
ANSWER_DRAIN_SECONDS = 1.2
# If speech restarts inside the drain window, wait at most this long for its
# transcription before advancing with what we have.
ANSWER_CONTINUATION_TIMEOUT = 20.0

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
    return {
        "type": "realtime",
        "model": settings.REALTIME_MODEL,
        "instructions": _session_instructions(language),
        "audio": {
            "input": {
                "transcription": transcription,
                "turn_detection": {
                    "type": "server_vad",
                    "create_response": False,
                    "interrupt_response": True,
                    "silence_duration_ms": 800,
                },
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

    def _speak(self, ws, text: str) -> None:
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
        waiting_for_continuation = False
        wait_until = time.monotonic() + ANSWER_DRAIN_SECONDS
        while time.monotonic() < min(wait_until, self.deadline):
            event = self._recv_event(ws, timeout=0.25)
            if event is None:
                if not waiting_for_continuation:
                    continue
                continue
            etype = event.get("type", "")
            if etype == "input_audio_buffer.speech_started":
                waiting_for_continuation = True
                wait_until = time.monotonic() + ANSWER_CONTINUATION_TIMEOUT
            elif self._is_transcript_done(event):
                text = (event.get("transcript") or "").strip()
                if text:
                    parts.append(text)
                waiting_for_continuation = False
                wait_until = time.monotonic() + ANSWER_DRAIN_SECONDS
            elif etype == "response.done":
                self._on_response_done(event)
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
        transcript = self._collect_answer(ws, transcript) if transcript else ""
        if not transcript:
            self._speak(ws, _repeat_line(self.language))
            return
        result = _advance_turn(self.participant_id, transcript)
        if result is None:
            self._speak(ws, _repeat_line(self.language))
            return
        if result.get("is_complete"):
            self.closing = True
        self._speak(ws, result["question_text"])

    # -- main loop ----------------------------------------------------------

    def run(self) -> None:
        try:
            with self._connect() as ws:
                logger.info(
                    "realtime sideband attached call=%s participant=%s",
                    self.call_id, self.participant_id,
                )
                opening = _pending_question(self.participant_id)
                if opening:
                    self._speak(ws, opening)
                while time.monotonic() < self.deadline:
                    event = self._recv_event(ws, timeout=30.0)
                    if event is None:
                        continue
                    etype = event.get("type", "")
                    if self._is_transcript_done(event):
                        self._handle_transcript(ws, event)
                    elif etype.endswith("input_audio_transcription.failed"):
                        self._speak(ws, _repeat_line(self.language))
                    elif etype == "response.done":
                        self._on_response_done(event)
                    elif etype == "error":
                        logger.warning(
                            "realtime event error for participant %s: %s",
                            self.participant_id, json.dumps(event)[:500],
                        )
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
    """Transcode (if needed) and store the browser's full-session capture."""
    from app.services.storage import upload_audio
    from app.services.transcode import needs_transcode, transcode_to_mp3

    if needs_transcode(ext):
        converted = transcode_to_mp3(data, ext)
        if converted is not None:
            data, ext = converted, ".mp3"
    key = f"recordings/{participant.id}/session-{uuid.uuid4().hex}{ext}"
    url = upload_audio(data, key)
    participant.session_recording_url = url
    db.commit()
    return url
