"""Realtime beta: cut the session recording into classic per-turn artifacts.

Classic interviews give the researcher a per-turn answer player
(``InterviewTurn.audio_recording_url``) and sentence-level highlight/seek
(``response_segments`` from Whisper). Realtime interviews record one file
per connection instead — but the sideband stamps every turn with its
answer's span inside that file, so once the interview completes we can cut
each answer out with ffmpeg and run Whisper over the clip. That fills the
exact fields the classic Responses view reads, making the researcher
experience identical for both transports with zero UI changes.

``response_transcript`` is deliberately left alone: it is the text the live
transcriber produced and the interview engine actually responded to. The
Whisper pass only supplies timing segments (whose own text drives the
highlight layer, same as classic).

Runs as a daemon thread from the recording upload endpoint once the
participant is completed. Idempotent: turns that already have a clip are
skipped, and a re-upload of a longer file retries only the turns still
missing one. Best-effort throughout — a slicing failure never loses the
session recording or the transcript.
"""

import json
import logging
import subprocess
import threading
import uuid

logger = logging.getLogger(__name__)

# Breathing room around the VAD-derived span so the first and last words
# are never clipped mid-syllable.
CLIP_PAD_SECONDS = 0.75
# A produced clip smaller than this is a slice past the end of the data
# (upload still growing) or an ffmpeg failure: skip, retry on next upload.
MIN_CLIP_BYTES = 1_000


def _slice_mp3(data: bytes, start: float, end: float) -> bytes | None:
    """Cut [start, end] seconds out of an mp3; None when unavailable."""
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{max(0.0, start):.2f}", "-to", f"{end:.2f}",
                "-i", "pipe:0",
                "-vn", "-acodec", "libmp3lame", "-b:a", "64k",
                "-f", "mp3", "pipe:1",
            ],
            input=data,
            capture_output=True,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("ffmpeg unavailable for realtime turn slicing")
        return None
    if result.returncode != 0 or len(result.stdout) < MIN_CLIP_BYTES:
        return None
    return result.stdout


def slice_turn_clips(
    participant_id: str, data: bytes, segment_key: str | None
) -> int:
    """Cut per-turn answer clips from one segment's recording. Returns the
    number of turns that gained a clip."""
    from app.database import session_scope
    from app.models.interview import InterviewTurn, Participant
    from app.services.storage import upload_audio
    from app.services.stt import transcribe_audio
    from app.services.usage_logger import log_stt_usage

    sliced = 0
    with session_scope() as db:
        participant = (
            db.query(Participant).filter(Participant.id == participant_id).first()
        )
        if participant is None:
            return 0
        project = participant.project
        language = (project.language if project else None) or None
        turns = (
            db.query(InterviewTurn)
            .filter(
                InterviewTurn.participant_id == participant_id,
                InterviewTurn.audio_recording_url.is_(None),
                InterviewTurn.answer_offset_seconds.isnot(None),
                InterviewTurn.answer_end_seconds.isnot(None),
                InterviewTurn.response_transcript.isnot(None),
            )
            .order_by(InterviewTurn.turn_index)
            .all()
        )
        # Spans are relative to their own segment's file: only slice turns
        # recorded by THIS connection (None matches only legacy None turns).
        turns = [t for t in turns if t.audio_segment_key == segment_key]
        for turn in turns:
            start = (turn.answer_offset_seconds or 0.0) - CLIP_PAD_SECONDS
            end = (turn.answer_end_seconds or 0.0) + CLIP_PAD_SECONDS
            clip = _slice_mp3(data, start, end)
            if clip is None:
                continue
            key = f"recordings/{participant_id}/turn-{turn.turn_index}-{uuid.uuid4().hex[:8]}.mp3"
            try:
                url = upload_audio(clip, key)
            except Exception:
                logger.exception(
                    "turn clip upload failed participant=%s turn=%s",
                    participant_id, turn.turn_index,
                )
                continue
            turn.audio_recording_url = url
            # Sentence segments for highlight/seek, exactly like classic.
            # The live transcript stays the record; Whisper only supplies
            # timing (its segments carry their own text for display).
            if not turn.response_segments:
                try:
                    _, duration, segments = transcribe_audio(
                        clip, filename="clip.mp3", language=language
                    )
                    if segments:
                        turn.response_segments = json.dumps(segments)
                    log_stt_usage(
                        db, duration,
                        company_id=project.company_id if project else None,
                        project_id=participant.project_id,
                        participant_id=participant_id,
                    )
                except Exception:
                    logger.warning(
                        "clip transcription failed participant=%s turn=%s (clip kept)",
                        participant_id, turn.turn_index,
                    )
            db.commit()
            sliced += 1
    if sliced:
        logger.info(
            "realtime: sliced %d per-turn answer clips participant=%s segment=%s",
            sliced, participant_id, segment_key,
        )
    return sliced


def spawn_turn_slicer(participant_id: str, data: bytes, segment_key: str | None) -> None:
    """Fire-and-forget slicing after a completed interview's upload."""
    threading.Thread(
        target=lambda: _safe_slice(participant_id, data, segment_key),
        daemon=True,
        name=f"rt-slice-{participant_id[:8]}",
    ).start()


def _safe_slice(participant_id: str, data: bytes, segment_key: str | None) -> None:
    try:
        slice_turn_clips(participant_id, data, segment_key)
    except Exception:
        logger.exception("realtime turn slicing crashed participant=%s", participant_id)
