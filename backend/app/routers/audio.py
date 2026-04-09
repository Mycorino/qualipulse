import os

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(prefix="/audio", tags=["audio"])


ALLOWED_EXTENSIONS = {".mp3", ".webm", ".ogg", ".wav", ".mp4", ".m4a"}


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
