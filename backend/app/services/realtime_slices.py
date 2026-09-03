"""Realtime beta: cut the session recording into classic per-turn artifacts.

Classic interviews give the researcher a per-turn answer player
(``InterviewTurn.audio_recording_url``) and sentence-level highlight/seek
(``response_segments`` from Whisper). Realtime interviews record one file
per connection instead, but the sideband stamps every turn with its
answer's span inside that file, so each answer can be cut out with ffmpeg
and run through Whisper. That fills the exact fields the classic Responses
view reads, making the researcher experience identical for both transports
with zero UI changes.

Slicing is **incremental**: the client re-uploads its growing recording
every ~45s, and every upload cuts the answers that are now fully inside the
file. Cutting only at completion (the first version) meant a session that
never reached its closing line, which is every abandoned or cut-short live
session, never got a single clip; and a researcher watching a live
interview sees per-turn audio within a minute of each answer instead of
after the goodbye. An answer whose span runs past the end of the uploaded
audio (still being spoken, or ended within the safety margin) is left for
the next upload rather than cut short.

``response_transcript`` is deliberately left alone: it is the text the live
transcriber produced and the interview engine actually responded to. The
Whisper pass only supplies timing segments (whose own text drives the
highlight layer, same as classic).

Runs as a daemon thread from the recording upload endpoint. Idempotent:
turns that already have a clip are skipped, and slicers for the same
participant run one at a time so two overlapping uploads never cut the
same answer twice. Best-effort throughout: a slicing failure never loses
the session recording or the transcript.
"""

import logging
import os
import subprocess
import tempfile
import threading
import uuid
from collections import defaultdict

logger = logging.getLogger(__name__)

# Breathing room around the VAD-derived span so the first and last words
# are never clipped mid-syllable.
CLIP_PAD_SECONDS = 0.75
# An answer must end this far before the end of the uploaded audio before
# it is cut from an in-progress upload: the tail of a growing file is the
# part most likely to still be mid-word. A completed interview's final
# upload cuts everything.
END_SAFETY_SECONDS = 0.5
# A produced clip smaller than this is a slice past the end of the data or
# an ffmpeg failure: skip, retry on next upload.
MIN_CLIP_BYTES = 1_000

# One lock per participant so overlapping uploads (a 45s interval upload
# racing the tab-hide flush) slice sequentially and the second sees the
# first's clips already written.
_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_locks_guard = threading.Lock()


def _participant_lock(participant_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks[participant_id]


def _probe_duration(path: str) -> float | None:
    """Seconds of audio in the file; None when ffprobe is unavailable."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            capture_output=True,
            timeout=30,
        )
        return float(result.stdout.decode().strip()) if result.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return None


def _slice_clip(path: str, start: float, end: float) -> bytes | None:
    """Cut [start, end] seconds out of the recording as mp3; None on failure.

    File input rather than a pipe: a MediaRecorder mp4 keeps its index at
    the end of the file, which ffmpeg cannot reach through stdin.
    """
    start = max(0.0, start)
    if end <= start:
        return None
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-ss", f"{start:.2f}",
                "-i", path,
                "-t", f"{end - start:.2f}",
                "-vn", "-acodec", "libmp3lame", "-b:a", "64k",
                "-f", "mp3", "pipe:1",
            ],
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
    participant_id: str,
    data: bytes,
    segment_key: str | None,
    ext: str = ".mp3",
    *,
    completed: bool = False,
) -> int:
    """Cut per-turn answer clips from one segment's recording. Returns the
    number of turns that gained a clip.

    ``completed`` marks the final upload of a finished interview: every
    remaining span is cut, end-of-file safety margin included. Otherwise
    only answers that ended safely before the end of the audio are cut.
    """
    from app.database import session_scope
    from app.models.interview import InterviewTurn, Participant
    from app.services.storage import upload_audio
    from app.services.stt import transcribe_audio
    from app.services.usage_logger import log_stt_usage

    if not ext.startswith("."):
        ext = "." + ext
    sliced = 0
    path = None
    with _participant_lock(participant_id):
        try:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(data)
                path = f.name
            duration = _probe_duration(path)
            if duration is None and not completed:
                # Cannot tell where the audio ends: cutting blind from a
                # growing file risks a truncated clip, so wait for the
                # final upload, which cuts everything.
                return 0
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
                # Spans are relative to their own segment's file: only slice
                # turns recorded by THIS connection (None matches only legacy
                # None turns).
                turns = [t for t in turns if t.audio_segment_key == segment_key]
                for turn in turns:
                    start = (turn.answer_offset_seconds or 0.0) - CLIP_PAD_SECONDS
                    end = (turn.answer_end_seconds or 0.0) + CLIP_PAD_SECONDS
                    if not completed and duration is not None and end + END_SAFETY_SECONDS > duration:
                        # Still being spoken, or too close to the end of
                        # what has been uploaded: next upload.
                        continue
                    clip = _slice_clip(path, start, end)
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
                    # Sentence segments for highlight/seek, exactly like
                    # classic. The live transcript stays the record; Whisper
                    # only supplies timing (its segments carry their own
                    # text for display).
                    if not turn.response_segments:
                        try:
                            _, clip_seconds, segments = transcribe_audio(
                                clip, filename="clip.mp3", language=language
                            )
                            if segments:
                                import json

                                turn.response_segments = json.dumps(segments)
                            log_stt_usage(
                                db, clip_seconds,
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
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
    if sliced:
        logger.info(
            "realtime: sliced %d per-turn answer clips participant=%s segment=%s completed=%s",
            sliced, participant_id, segment_key, completed,
        )
    return sliced


def spawn_turn_slicer(
    participant_id: str,
    data: bytes,
    segment_key: str | None,
    ext: str = ".mp3",
    *,
    completed: bool = False,
) -> None:
    """Fire-and-forget slicing after every recording upload."""
    threading.Thread(
        target=lambda: _safe_slice(participant_id, data, segment_key, ext, completed),
        daemon=True,
        name=f"rt-slice-{participant_id[:8]}",
    ).start()


def _safe_slice(participant_id, data, segment_key, ext, completed) -> None:
    try:
        slice_turn_clips(participant_id, data, segment_key, ext, completed=completed)
    except Exception:
        logger.exception("realtime turn slicing crashed participant=%s", participant_id)
