import os
from pathlib import Path

from app.config import settings


def save_audio(file_data: bytes, filename: str, subfolder: str = "") -> str:
    """Save audio data to disk and return the relative path."""
    rel_dir = os.path.join(subfolder) if subfolder else ""
    abs_dir = os.path.join(settings.UPLOAD_DIR, rel_dir)
    os.makedirs(abs_dir, exist_ok=True)

    rel_path = os.path.join(rel_dir, filename) if rel_dir else filename
    abs_path = os.path.join(settings.UPLOAD_DIR, rel_path)

    with open(abs_path, "wb") as f:
        f.write(file_data)

    return rel_path


def get_audio_path(relative_path: str) -> str:
    """Return the absolute path for a given relative audio path."""
    return os.path.join(os.path.abspath(settings.UPLOAD_DIR), relative_path)
