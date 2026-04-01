"""Audio storage — local disk or Cloudflare R2 (S3-compatible).

Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET, and
R2_PUBLIC_URL in .env to enable R2. When those vars are absent the service
falls back to local disk (UPLOAD_DIR).
"""

import os

import boto3
from botocore.config import Config

from app.config import settings


def _r2_enabled() -> bool:
    return bool(
        settings.R2_ACCOUNT_ID
        and settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.R2_BUCKET
    )


def _r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
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


def download_audio(key: str) -> bytes:
    """Retrieve audio bytes by the key used when uploading."""
    if _r2_enabled():
        resp = _r2_client().get_object(Bucket=settings.R2_BUCKET, Key=key)
        return resp["Body"].read()
    else:
        abs_path = os.path.join(settings.UPLOAD_DIR, key)
        with open(abs_path, "rb") as f:
            return f.read()


def _content_type(key: str) -> str:
    ext = os.path.splitext(key)[1].lower()
    return {
        ".mp3": "audio/mpeg",
        ".mp4": "audio/mp4",
        ".webm": "audio/webm",
        ".ogg": "audio/ogg",
        ".wav": "audio/wav",
    }.get(ext, "application/octet-stream")
