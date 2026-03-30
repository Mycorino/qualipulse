import os

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(prefix="/audio", tags=["audio"])


@router.get("/{path:path}")
def serve_audio(path: str):
    """Serve an audio file from the uploads directory."""
    abs_path = os.path.join(os.path.abspath(settings.UPLOAD_DIR), path)

    # Prevent directory traversal
    upload_root = os.path.abspath(settings.UPLOAD_DIR)
    if not os.path.abspath(abs_path).startswith(upload_root):
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
