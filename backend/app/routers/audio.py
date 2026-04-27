import io
import logging
import os
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.dependencies import get_db
from app.models.interview import InterviewTurn
from app.services.storage import upload_audio
from app.services.tts import generate_speech_streaming
from app.services.usage_logger import log_tts_usage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["audio"])


ALLOWED_EXTENSIONS = {".mp3", ".webm", ".ogg", ".wav", ".mp4", ".m4a"}


def _persist_tts_to_r2(turn_id: str, audio_bytes: bytes) -> None:
    """Background task: upload streamed TTS bytes to R2 + log usage.

    Uses its own DB session because the request session is closed by the time
    the StreamingResponse generator finishes.
    """
    if not audio_bytes:
        return
    db: Session = SessionLocal()
    try:
        turn = db.query(InterviewTurn).filter(InterviewTurn.id == turn_id).first()
        if turn is None:
            return
        key = f"tts/{turn.participant_id}/{uuid.uuid4().hex}.mp3"
        try:
            url = upload_audio(audio_bytes, key)
        except Exception:
            logger.exception("Failed to upload streamed TTS to storage for turn %s", turn_id)
            return
        turn.tts_audio_url = url
        db.commit()

        # Log TTS usage once per turn (idempotent guard: only if question_text exists)
        try:
            participant = turn.participant
            project = participant.project if participant else None
            log_tts_usage(
                db,
                turn.question_text or "",
                company_id=project.company_id if project else None,
                project_id=project.id if project else None,
                participant_id=turn.participant_id,
            )
        except Exception:
            pass
    finally:
        db.close()


@router.get("/stream/{turn_id}")
def stream_tts_for_turn(turn_id: str, db: Session = Depends(get_db)):
    """Stream TTS audio for an interview turn's question_text.

    Streams MP3 chunks via HTTP chunked transfer. Tees bytes to a buffer and
    uploads to R2 in a background thread once the stream completes, so the turn
    ends up with a persistent tts_audio_url for replay.
    """
    turn = db.query(InterviewTurn).filter(InterviewTurn.id == turn_id).first()
    if turn is None or not (turn.question_text or "").strip():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Turn not found or has no question text",
        )

    question_text = turn.question_text

    def generate():
        buffer = io.BytesIO()
        completed = False
        try:
            for chunk in generate_speech_streaming(question_text):
                buffer.write(chunk)
                yield chunk
            completed = True
        except GeneratorExit:
            # Client aborted mid-stream — don't persist partial audio.
            return
        except Exception:
            logger.exception("TTS streaming failed for turn %s", turn_id)
            return
        finally:
            if completed:
                # Background-upload only when the stream finished cleanly.
                audio_bytes = buffer.getvalue()
                threading.Thread(
                    target=_persist_tts_to_r2,
                    args=(turn_id, audio_bytes),
                    daemon=True,
                ).start()

    return StreamingResponse(
        generate(),
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{path:path}")
def serve_audio(path: str):
    """Serve an audio file from the uploads directory."""
    # Extension whitelist
    _, ext = os.path.splitext(path)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="File type not allowed",
        )

    upload_root = os.path.realpath(settings.UPLOAD_DIR)
    abs_path = os.path.realpath(os.path.join(upload_root, path))

    # Prevent directory traversal (realpath resolves symlinks)
    if not abs_path.startswith(upload_root + os.sep) and abs_path != upload_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )

    if not os.path.isfile(abs_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found",
        )

    return FileResponse(abs_path)
