"""Audio storage — local disk or Cloudflare R2 (S3-compatible).

Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, and
R2_PUBLIC_URL in .env to enable R2. When those vars are absent the service
falls back to local disk (UPLOAD_DIR).
"""

import logging
import os

import boto3
from botocore.config import Config

from app.config import settings

logger = logging.getLogger(__name__)


def _r2_enabled() -> bool:
    return bool(
        settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_BUCKET
    )


def _r2_client():
    jurisdiction = (settings.R2_JURISDICTION or "").strip().lower()
    host = f"{settings.R2_ACCOUNT_ID}.{jurisdiction}.r2.cloudflarestorage.com" if jurisdiction \
        else f"{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=f"https://{host}",
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_audio(data: bytes, key: str) -> str:
    """Store audio bytes and return the URL to persist in the database.

    key should be a relative path like 'tts/{participant_id}/{uuid}.mp3'
    """
    if _r2_enabled():
        _r2_client().put_object(
            Bucket=settings.R2_BUCKET,
            Key=key,
            Body=data,
            ContentType=_content_type(key),
        )
        base = settings.R2_PUBLIC_URL.rstrip("/")
        return f"{base}/{key}"
    else:
        abs_path = os.path.join(settings.UPLOAD_DIR, key)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(data)
        return f"/audio/{key}"


def upload_image(data: bytes, key: str) -> str:
    """Store image bytes and return the URL to embed in content.

    key should be a relative path like 'blog-images/{uuid}.png'.
    R2 returns the absolute public URL; local disk returns '/api/files/{key}'
    (the /api prefix is stripped by the Vite dev proxy and the production
    nginx, landing on the backend /files route).
    """
    if _r2_enabled():
        _r2_client().put_object(
            Bucket=settings.R2_BUCKET,
            Key=key,
            Body=data,
            ContentType=_content_type(key),
        )
        base = settings.R2_PUBLIC_URL.rstrip("/")
        return f"{base}/{key}"
    else:
        abs_path = os.path.join(settings.UPLOAD_DIR, key)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "wb") as f:
            f.write(data)
        return f"/api/files/{key}"


def storage_key_from_url(url: str) -> str | None:
    """Recover the storage key from a persisted playback URL.

    Inverse of `upload_audio`'s return value. Handles both the R2 form
    (`{R2_PUBLIC_URL}/{key}`) and the local-disk form (`/audio/{key}`).
    Returns None if the URL doesn't match a known shape.
    """
    if not url:
        return None
    if _r2_enabled():
        base = settings.R2_PUBLIC_URL.rstrip("/") + "/"
        if url.startswith(base):
            return url[len(base):]
    if url.startswith("/audio/"):
        return url[len("/audio/"):]
    # R2 public URL may differ from the one configured now (or disk→R2 switch):
    # fall back to treating everything after the last "/audio/" or host as key.
    if "/audio/" in url:
        return url.split("/audio/", 1)[1]
    return None


def delete_audio(key: str) -> bool:
    """Best-effort deletion of a stored audio object by its storage key.

    Returns True when the delete call succeeded (R2's delete_object is
    idempotent; a local missing file counts as failure=False). Never raises:
    GDPR cascades must not abort because one blob is already gone.
    """
    if not key:
        return False
    try:
        if _r2_enabled():
            _r2_client().delete_object(Bucket=settings.R2_BUCKET, Key=key)
            return True
        upload_root = os.path.realpath(settings.UPLOAD_DIR)
        abs_path = os.path.realpath(os.path.join(upload_root, key))
        # Path-traversal protection: refuse anything resolving outside UPLOAD_DIR.
        if abs_path != upload_root and not abs_path.startswith(upload_root + os.sep):
            logger.warning("delete_audio refused key outside UPLOAD_DIR: %r", key)
            return False
        if os.path.isfile(abs_path):
            os.remove(abs_path)
            return True
        return False
    except Exception:
        logger.warning("delete_audio failed for key=%r", key, exc_info=True)
        return False


def delete_audio_by_url(url: str) -> bool:
    """Best-effort deletion by the persisted playback URL (see delete_audio)."""
    key = storage_key_from_url(url) if url else None
    if not key:
        return False
    return delete_audio(key)


def download_audio(key: str) -> bytes:
    """Retrieve audio bytes by the key used when uploading."""
    if _r2_enabled():
        resp = _r2_client().get_object(Bucket=settings.R2_BUCKET, Key=key)
        return resp["Body"].read()
    else:
        abs_path = os.path.join(settings.UPLOAD_DIR, key)
        with open(abs_path, "rb") as f:
            return f.read()


# ── Image upload validation (shared by blog editor + project logo upload) ─────
MAX_IMAGE_UPLOAD_MB = 8
IMAGE_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def matches_image_magic(data: bytes, ext: str) -> bool:
    """Cheap signature check so a mislabelled file can't be stored as an image."""
    if ext == ".png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".jpg":
        return data.startswith(b"\xff\xd8\xff")
    if ext == ".gif":
        return data.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def _content_type(key: str) -> str:
    ext = os.path.splitext(key)[1].lower()
    return {
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }.get(ext, "application/octet-stream")
