"""Backfill audio_recording_url with full URLs.

A bug in interview_engine.process_interview_turn stored just the storage
key (e.g. ``recordings/{participant_id}/{uuid}.webm``) on
``InterviewTurn.audio_recording_url`` instead of the full playback URL
returned by the storage layer. The audio files were uploaded to R2 fine
— only the DB column was malformed, so the frontend's <audio> element
hit 404s. This migration prefixes any bare-key value with R2_PUBLIC_URL
so existing recordings become playable again. Rows that already store a
full URL (``http://...``, ``https://...``) or a local-dev path
(``/audio/...``) are left untouched.

Revision ID: 0020_fix_audio_recording_urls
Revises: 0019_warmup_enabled
Create Date: 2026-05-03
"""
import os

from alembic import op


revision = "0020_fix_audio_recording_urls"
down_revision = "0019_warmup_enabled"
branch_labels = None
depends_on = None


def upgrade() -> None:
    public_url = (os.environ.get("R2_PUBLIC_URL") or "").rstrip("/")
    if not public_url:
        # Local dev / R2 not configured — nothing to backfill. Leave bare
        # keys as-is; the legacy /audio/{key} route still serves them.
        return

    op.execute(
        f"""
        UPDATE interview_turns
        SET audio_recording_url = '{public_url}/' || audio_recording_url
        WHERE audio_recording_url IS NOT NULL
          AND audio_recording_url <> ''
          AND audio_recording_url NOT LIKE 'http://%'
          AND audio_recording_url NOT LIKE 'https://%'
          AND audio_recording_url NOT LIKE '/audio/%'
        """
    )


def downgrade() -> None:
    public_url = (os.environ.get("R2_PUBLIC_URL") or "").rstrip("/")
    if not public_url:
        return
    op.execute(
        f"""
        UPDATE interview_turns
        SET audio_recording_url = REPLACE(audio_recording_url, '{public_url}/', '')
        WHERE audio_recording_url LIKE '{public_url}/%'
        """
    )
