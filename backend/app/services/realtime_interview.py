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

Every line the model speaks is an **isolated** response (``input: []``): the
model is handed the text and nothing else. Given the running conversation as
context, gpt-realtime stops reading the host line verbatim once the
conversation has some history, and starts answering the participant itself:
it paraphrases the question into a validating summary ("Exactly, so you
coordinate and check the agents' work, and that keeps you in control..."),
and turns the two-word acknowledgment into a whole improvised follow-up the
participant hears but never sees captioned. That is the "every question is
asked twice, and the interviewer keeps agreeing with me" failure. With no
context there is nothing to react to, so the line comes out verbatim.

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
from websockets.exceptions import ConnectionClosed

from app.config import settings

logger = logging.getLogger(__name__)

REALTIME_CALLS_URL = "https://api.openai.com/v1/realtime/calls"
REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"

# Floor for the session watchdog: even a "5 minute" study gets this long
# before the sideband hangs up, so setup fumbling never kills a real session.
MIN_SESSION_MINUTES = 20.0

# End-of-answer detection lives in settings.REALTIME_ANSWER_SILENCE_SECONDS:
# silence measured from the participant's last speech_stopped, not from a
# transcript's arrival (transcription lags speech by 1-2s and says nothing
# about whether they are still thinking). Once quiet long enough, we still
# wait at most this long for any committed burst whose transcription has not
# come back yet before advancing with what we have.
ANSWER_CONTINUATION_TIMEOUT = 20.0

# An answer this short (in words) is usually a thought being formed, not a
# finished answer: require this much extra silence before advancing.
SHORT_ANSWER_WORDS = 4
SHORT_ANSWER_EXTRA_WAIT = 2.0

# Speaker-to-mic echo: for this long after the interviewer stops speaking, a
# transcript that echoes what it just said is treated as the room hearing the
# interviewer, not the participant answering. Measured from response.done,
# which fires when *generation* ends — the phone's speaker keeps playing the
# buffered tail for a while after that, and the echo's transcription takes a
# few more seconds to come back, so this window has to absorb both lags.
ECHO_TAIL_SECONDS = 6.0
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


def _verbatim_instruction(text: str, language: str | None) -> str:
    """Response instructions for one spoken line.

    ``response.instructions`` REPLACES the session instructions for that
    response, and the response is created with no conversation context, so
    the persona and the language have to travel with every line.
    """
    return (
        _session_instructions(language)
        + " Say exactly the following line to the participant, verbatim, "
        "warmly and naturally. Do not add, remove, or change anything:\n"
        + text
    )


def _isolated_response(instructions: str, **extra) -> dict:
    """A ``response.create`` payload with an empty context.

    ``input: []`` is the load-bearing bit (see the module docstring): the
    model sees only these instructions, never the conversation, so it cannot
    react to the participant, paraphrase, or improvise a second question.
    """
    payload = {"type": "response.create", "response": {"instructions": instructions, "input": [], **extra}}
    return payload


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
        # unfinished. Eagerness only sets how promptly it reports the end
        # of speech; the burst patience lives in _collect_answer, measured
        # from that event, so the VAD no longer needs to be slow as well.
        turn_detection = {
            "type": "semantic_vad",
            "eagerness": settings.REALTIME_VAD_EAGERNESS,
            "create_response": False,
            "interrupt_response": settings.REALTIME_ALLOW_BARGE_IN,
        }
    audio_input: dict = {
        "transcription": transcription,
        "turn_detection": turn_detection,
    }
    if settings.REALTIME_NOISE_REDUCTION:
        # Filters the input buffer before it reaches VAD, so room noise and
        # speaker bleed are less likely to commit as participant speech.
        audio_input["noise_reduction"] = {"type": settings.REALTIME_NOISE_REDUCTION}
    return {
        "type": "realtime",
        "model": settings.REALTIME_MODEL,
        "instructions": _session_instructions(language),
        "audio": {
            "input": audio_input,
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


# The "I heard you" beat spoken while Claude decides the next line. Fixed,
# neutral listening words (never praise, never agreement): every one of them
# is also in the hesitation sets below, so should the speaker leak one back
# into the microphone it is held as a non-answer rather than fed to Claude.
# Rotated per turn so the participant does not hear the same word every time.
_ACK_LINES = {
    "en": ("Okay.", "I see.", "Got it."),
    "fr": ("D'accord.", "Je vois.", "Entendu."),
    "de": ("Okay.", "Verstehe.", "Alles klar."),
    "es": ("Vale.", "Entiendo.", "Ya veo."),
    "it": ("Va bene.", "Capisco.", "Certo."),
    "pt": ("Certo.", "Entendo.", "Estou a ver."),
}


def _ack_line(language: str | None, turn: int) -> str:
    lang = (language or "en")[:2]
    lines = _ACK_LINES.get(lang, _ACK_LINES["en"])
    return lines[turn % len(lines)]


def _ack_instruction(language: str | None, turn: int = 0) -> str:
    return _verbatim_instruction(_ack_line(language, turn), language)


def _backchannel_instruction(language: str | None) -> str:
    lang = (language or "en")[:2]
    return (
        _session_instructions(language)
        + f" Make ONE soft, short listening sound in the interview language ({lang}), "
        f"like 'Mm-hm.', under one second, warm, a nod rather than a word. "
        f"No words, no question, nothing else."
    )


# Hesitation particles and bare acknowledgments, per language. A transcript
# made ONLY of these is someone thinking out loud (or the interviewer's own
# "Got it." leaking through the speaker), never a finished answer. Real short
# answers ("No.", "Netflix.") contain at least one word outside these sets.
_UNIVERSAL_FILLERS = {"ah", "eh", "er", "hm", "hmm", "mm", "mmm", "uh", "um", "oh", "ok", "okay"}
_HESITATION_WORDS = {
    "en": {"so", "well", "like", "gotcha", "right", "sure", "alright", "see", "got", "it", "i"},
    "fr": {"euh", "ben", "bah", "hum", "alors", "donc", "bon", "hein", "voila", "voilà",
           "d'accord", "daccord", "compris", "entendu", "vois", "je", "bien", "très", "tres", "parfait"},
    "de": {"äh", "ähm", "also", "tja", "na", "gut", "klar", "verstehe", "alles"},
    "es": {"em", "este", "pues", "bueno", "vale", "entiendo", "ver", "muy", "bien", "a", "ya", "veo"},
    "it": {"ehm", "mah", "beh", "allora", "dunque", "cioè", "cioe", "capisco", "va", "bene", "certo"},
    "pt": {"hum", "então", "entao", "pois", "bem", "tipo", "certo", "entendo", "muito", "estou", "a", "ver"},
}


def _is_hesitation_only(transcript: str, language: str | None) -> bool:
    """True when a transcript carries no answer content at all.

    "So", "Ah.", "Euh..." are the sound of a participant lining up a thought;
    treating them as answers makes the interviewer barrel ahead mid-thought
    (Claude probes "take your time..." while the participant is taking it).
    Such fragments must hold the turn open, silently.
    """
    words = re.sub(r"[^\w\s'À-ÿ]", " ", (transcript or "").lower()).split()
    if not words:
        return True
    lang = (language or "en")[:2]
    fillers = _UNIVERSAL_FILLERS | _HESITATION_WORDS.get(lang, _HESITATION_WORDS["en"])
    return all(w in fillers for w in words)


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


def _stamp_turn_offset(
    participant_id: str,
    turn_index: int | None,
    seconds: float,
    segment_key: str | None = None,
    overwrite: bool = False,
) -> None:
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
            if turn is not None and (overwrite or turn.audio_offset_seconds is None):
                turn.audio_offset_seconds = round(max(0.0, seconds), 1)
                if segment_key:
                    turn.audio_segment_key = segment_key
                db.commit()
    except Exception:
        logger.exception("could not stamp audio offset for participant %s", participant_id)


def _stamp_answer_span(
    participant_id: str,
    turn_index: int | None,
    start: float | None,
    end: float,
) -> None:
    """Record where a turn's ANSWER sits inside its recording segment.

    Last write wins (a resumed session re-answers the pending turn in a new
    segment, and the clip must come from where the kept answer lives). When
    no speech-start was observed, nothing is stamped — better no clip than
    a wrong one.
    """
    if turn_index is None or start is None or end <= start:
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
            if turn is not None:
                turn.answer_offset_seconds = round(max(0.0, start), 1)
                turn.answer_end_seconds = round(end, 1)
                db.commit()
    except Exception:
        logger.exception("could not stamp answer span for participant %s", participant_id)


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
                # The line will be spoken aloud: ask the engine for a
                # conversational, sub-25-word question, not a written one.
                spoken_live=True,
            )
    except EmptyTranscriptError:
        return None


class SidebandBridge:
    """One realtime call's server-side driver.

    Owns the sideband WebSocket, replays queued events, and turns each
    completed input transcription into a Claude-decided next line.
    """

    def __init__(
        self,
        call_id: str,
        participant_id: str,
        total_minutes: int | None,
        segment_key: str | None = None,
    ):
        self.call_id = call_id
        self.participant_id = participant_id
        # This connection's recording segment: stamped onto every turn so
        # its offset seeks into the right part of a multi-connection
        # (resumed) interview.
        self.segment_key = segment_key
        budget = max(MIN_SESSION_MINUTES, (total_minutes or 0) * settings.REALTIME_MAX_SESSION_FACTOR)
        self.deadline = time.monotonic() + budget * 60
        self.language = _interview_language(participant_id)
        self.closing = False
        # Half-duplex bookkeeping: what the interviewer is saying right now
        # (so its echo can be recognised) and whether a response is in
        # flight (so two lines never race for the same audio channel).
        self.response_active = False
        self.last_spoken = ""
        # What the model ACTUALLY said in its last few responses (from its
        # own output transcripts), acks included: the echo guard matches
        # against these as well as the planned line, so a leaked
        # acknowledgment or a slightly off rendering is still recognised.
        self.recent_outputs: list[str] = []
        self.last_response_ended_at = 0.0
        self._ack_turn = 0
        # Set when the sideband attaches — the zero point for per-turn
        # offsets into the client's session recording.
        self.session_started_at: float | None = None
        # When the participant started speaking the current answer (seconds
        # into this segment). With the answer-end time it becomes the span
        # the completion-time slicer cuts into a per-turn answer clip.
        self._answer_span_start: float | None = None
        # The answer gate: transcripts only count while a question is
        # actually awaiting its answer. Armed when a question (or repeat
        # request) finishes generating; disarmed the moment an answer is
        # accepted. Without it, the tail of an answer that VAD split — or
        # words spoken into the ack/thinking gap — arrives seconds later
        # and gets attributed to the question the participant has not
        # finished hearing, making the interviewer immediately re-ask a
        # near-identical question.
        self.awaiting_answer = False
        self._arm_on_response_done = False
        # Patience bookkeeping: is the participant mid-burst, when did their
        # last burst end, and how many committed bursts still owe us their
        # transcription. "Done answering" = quiet since the last burst for
        # REALTIME_ANSWER_SILENCE_SECONDS with nothing left in flight.
        self._speech_open = False
        self._last_speech_stopped_at: float | None = None
        self._pending_transcripts = 0

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
        # Every _speak line is a question or a repeat request — something
        # that expects an answer. Its response.done re-opens the gate.
        self._arm_on_response_done = True
        self._send(ws, _isolated_response(_verbatim_instruction(text, self.language)))

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
        elif etype == "response.output_audio_transcript.done":
            said = (event.get("transcript") or "").strip()
            if said:
                self.recent_outputs = (self.recent_outputs + [said])[-3:]
        elif etype == "input_audio_buffer.speech_started":
            self._speech_open = True
            # First speech after the interviewer went quiet = the answer
            # starting. Not reset by hesitation fragments — "So..." is the
            # beginning of the answer, and the clip should include it.
            if not self.response_active and self._answer_span_start is None:
                self._answer_span_start = self._session_elapsed()
        elif etype == "input_audio_buffer.speech_stopped":
            self._speech_open = False
            self._last_speech_stopped_at = time.monotonic()
        elif etype == "input_audio_buffer.committed":
            self._pending_transcripts += 1
        elif etype.endswith("input_audio_transcription.completed") or etype.endswith(
            "input_audio_transcription.failed"
        ):
            self._pending_transcripts = max(0, self._pending_transcripts - 1)
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
        if not speaking_recently:
            return False
        return any(
            _looks_like_echo(transcript, mine)
            for mine in [self.last_spoken, *self.recent_outputs]
            if mine
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

    def _backchannel(self, ws) -> None:
        """A soft "Mm-hm." while the participant thinks: we are listening.

        Out-of-band and tagged so the client neither captions it nor mutes
        the mic for it — the whole point is that they can keep talking.
        Its own response.done must not touch the answer gate.
        """
        if self.response_active:
            return
        self._arm_on_response_done = False
        self.response_active = True
        self._send(
            ws,
            _isolated_response(
                _backchannel_instruction(self.language),
                conversation="none",
                metadata={"kind": "backchannel"},
            ),
        )

    def _collect_answer(self, ws, first: str) -> str:
        """Concatenate transcripts until the participant has clearly finished.

        People narrate in bursts: a sentence, a 2-5s think, the next
        sentence. Semantic VAD commits at every sentence boundary, so "done"
        cannot mean "a transcript arrived" — it means
        REALTIME_ANSWER_SILENCE_SECONDS of quiet since their last words, with
        every committed burst transcribed. Answering the first burst alone
        was the cut-off the participants kept reporting: the rest of the
        thought landed on a muted mic and a closed gate.
        """
        parts = [first]
        entered = time.monotonic()
        silence = settings.REALTIME_ANSWER_SILENCE_SECONDS
        backchanneled = False
        while True:
            now = time.monotonic()
            if now >= self.deadline:
                break
            anchor = self._last_speech_stopped_at if self._last_speech_stopped_at is not None else entered
            quiet_for = 0.0 if self._speech_open else now - anchor
            combined = " ".join(p for p in parts if p)
            substantive = bool(combined) and not _is_hesitation_only(combined, self.language)
            if (
                settings.REALTIME_BACKCHANNEL_ENABLED
                and not backchanneled
                and substantive
                and quiet_for >= settings.REALTIME_BACKCHANNEL_AFTER_SECONDS
            ):
                backchanneled = True
                self._backchannel(ws)
            required = silence
            if substantive and len(combined.split()) < SHORT_ANSWER_WORDS:
                # A couple of words is usually a thought being formed.
                required += SHORT_ANSWER_EXTRA_WAIT
            if quiet_for >= required and (
                self._pending_transcripts == 0 or now - anchor >= ANSWER_CONTINUATION_TIMEOUT
            ):
                break
            event = self._recv_event(ws, timeout=0.25)
            if event is None:
                continue
            self._note_event(event)
            if self._is_transcript_done(event):
                text = (event.get("transcript") or "").strip()
                # Hesitation-only bursts ("euh", the backchannel's own echo)
                # add nothing to the answer text.
                if text and not self._is_echo(text) and not _is_hesitation_only(text, self.language):
                    parts.append(text)
        return " ".join(p for p in parts if p)

    def _on_response_done(self, event: dict) -> None:
        usage = (event.get("response") or {}).get("usage")
        if usage:
            _log_realtime_usage(self.participant_id, usage)
        if self._arm_on_response_done:
            # A question (or repeat request) has finished generating: from
            # here transcripts are answers. Playback still lags a little,
            # but the echo guard covers that tail.
            self._arm_on_response_done = False
            self.awaiting_answer = True
        if self.closing:
            # The wrap-up line has been fully spoken: the call is over.
            raise _SessionDone()

    def _handle_transcript(self, ws, event: dict) -> None:
        transcript = (event.get("transcript") or "").strip()
        if not self.awaiting_answer:
            # No question is waiting for an answer right now: this is the
            # tail of an already-accepted answer, or words spoken into the
            # ack/thinking gap, or the interviewer's own voice. Attributing
            # it to the question still being asked makes the interviewer
            # immediately re-ask a near-identical question — drop it.
            logger.info(
                "realtime: dropped out-of-turn transcript %r (participant=%s)",
                transcript[:80], self.participant_id,
            )
            return
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
            self.awaiting_answer = False
            self._answer_span_start = None
            self._speak(ws, _repeat_line(self.language))
            return
        if _is_hesitation_only(transcript, self.language):
            # "So", "Ah.", a stray "Okay" from the speaker: not an answer.
            # Say nothing, ask nothing, keep the turn open — the real answer
            # arrives as its own transcription event when they get there.
            logger.info(
                "realtime: holding turn open, hesitation-only fragment %r (participant=%s)",
                transcript[:60], self.participant_id,
            )
            return
        # This transcript IS the answer: close the gate and flush any audio
        # captured since the commit, so the trailing half-sentence of a
        # VAD-split answer can never surface later as a phantom reply to
        # the next question.
        self.awaiting_answer = False
        self._send(ws, {"type": "input_audio_buffer.clear"})
        if settings.REALTIME_ACK_ENABLED:
            # Fill the Claude-decision gap with a human "I heard you" beat
            # instead of silence. _speak below waits for this to finish, so
            # the question never talks over the acknowledgment. The ack is a
            # fixed neutral word spoken verbatim with no context (given the
            # conversation, the model turned "Got it." into a whole
            # improvised follow-up question of its own). last_spoken keeps
            # the previous question so its late echo stays matchable; the
            # ack's echo is caught by the hesitation gate and by
            # recent_outputs. The ack's own response.done must NOT re-open
            # the answer gate; only the question that follows may (its
            # _speak arms the flag).
            self._arm_on_response_done = False
            self.response_active = True
            self._send(
                ws,
                _isolated_response(
                    _ack_instruction(self.language, self._ack_turn),
                    # Out-of-band and tagged so the client does not caption it.
                    conversation="none",
                    metadata={"kind": "ack"},
                ),
            )
            self._ack_turn += 1
        # The turn being answered is the current pending one; capture it (and
        # the answer's span in this segment) before the engine advances.
        answered_index = _last_turn_index(self.participant_id)
        span_start, span_end = self._answer_span_start, self._session_elapsed()
        result = _advance_turn(self.participant_id, transcript)
        if result is None:
            self._answer_span_start = None
            self._speak(ws, _repeat_line(self.language))
            return
        self._answer_span_start = None
        _stamp_answer_span(self.participant_id, answered_index, span_start, span_end)
        if result.get("is_complete"):
            self.closing = True
        self._speak(ws, result["question_text"])
        _stamp_turn_offset(
            self.participant_id, result.get("turn_index"), self._session_elapsed(), self.segment_key
        )

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
                        self.participant_id,
                        _last_turn_index(self.participant_id),
                        self._session_elapsed(),
                        self.segment_key,
                        # A resumed session re-asks the pending question in
                        # THIS connection's recording; the old offset points
                        # into the previous segment, where no answer follows.
                        overwrite=True,
                    )
                while time.monotonic() < self.deadline:
                    event = self._recv_event(ws, timeout=30.0)
                    if event is None:
                        continue
                    etype = self._note_event(event)
                    if self._is_transcript_done(event):
                        self._handle_transcript(ws, event)
                    elif etype.endswith("input_audio_transcription.failed"):
                        # Only ask to repeat when an answer was actually
                        # due — a failed transcription of spillover audio
                        # must not interrupt the question being asked.
                        if self.awaiting_answer:
                            self.awaiting_answer = False
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
        except ConnectionClosed:
            # The participant closed the page (or OpenAI ended the call), so
            # the socket died under us: ordinary teardown, not a crash. The
            # interview stays resumable like any in-progress interview.
            logger.info(
                "realtime call closed call=%s participant=%s",
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


def spawn_sideband(
    call_id: str,
    participant_id: str,
    total_minutes: int | None,
    segment_key: str | None = None,
) -> None:
    bridge = SidebandBridge(call_id, participant_id, total_minutes, segment_key)
    threading.Thread(
        target=bridge.run, daemon=True, name=f"realtime-{participant_id[:8]}"
    ).start()


def store_session_recording(
    participant, data: bytes, ext: str, db, segment_key: str | None = None
) -> str:
    """Transcode (if needed) and store the browser's full-session capture.

    The client uploads incrementally (every ~45s and on tab hide), so this
    runs repeatedly per interview. Each browser connection owns one
    **segment** (identified by the segment_key minted at the SDP exchange):
    an upload replaces only its OWN segment's previous file, so a resumed
    session or a second tab can never overwrite or delete another
    connection's audio. That single-slot overwrite is exactly how a
    resumed interview once lost its morning recording, and a race between
    the interval upload and the tab-close flush once left the DB pointing
    at a deleted file. Fresh object key per upload (no stale CDN caching of
    a shorter file); participant.session_recording_url tracks the newest
    upload for legacy consumers.
    """
    from app.models.interview import RealtimeRecordingSegment
    from app.services.storage import delete_audio_by_url, upload_audio
    from app.services.transcode import needs_transcode, transcode_to_mp3

    if needs_transcode(ext):
        converted = transcode_to_mp3(data, ext)
        if converted is not None:
            data, ext = converted, ".mp3"
    key = f"recordings/{participant.id}/session-{uuid.uuid4().hex}{ext}"
    url = upload_audio(data, key)

    previous: str | None = None
    if segment_key:
        segment = (
            db.query(RealtimeRecordingSegment)
            .filter(
                RealtimeRecordingSegment.participant_id == participant.id,
                RealtimeRecordingSegment.segment_key == segment_key,
            )
            .first()
        )
        if segment is None:
            segment = RealtimeRecordingSegment(
                participant_id=participant.id, segment_key=segment_key, url=url
            )
            db.add(segment)
        else:
            previous = segment.url
            segment.url = url
    else:
        # Legacy client (pre-segments bundle): single-slot behaviour — but
        # never delete a file that a segment row owns (mixed old/new clients
        # can briefly coexist across a deploy).
        previous = participant.session_recording_url
        if previous is not None:
            owned = (
                db.query(RealtimeRecordingSegment)
                .filter(RealtimeRecordingSegment.url == previous)
                .first()
            )
            if owned is not None:
                previous = None
    participant.session_recording_url = url
    db.commit()
    if previous and previous != url:
        try:
            delete_audio_by_url(previous)
        except Exception:
            logger.warning("could not delete superseded session recording %s", previous)
    # Cut per-turn answer clips + Whisper segments from what has been
    # uploaded so far, so the researcher view matches classic while the
    # interview is still running (and for sessions that never reach the
    # closing line). Idempotent per turn; each upload cuts the answers now
    # fully inside the file, the completed upload cuts everything left.
    from app.services.realtime_slices import spawn_turn_slicer

    spawn_turn_slicer(
        participant.id, data, segment_key, ext, completed=participant.status == "completed"
    )
    return url
