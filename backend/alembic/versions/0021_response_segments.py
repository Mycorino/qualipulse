"""Add response_segments to interview_turns.

Stores Whisper's verbose_json segment timestamps as JSON text so the
researcher transcript view can highlight the segment currently playing
in sync with audio. Existing rows stay null and gracefully fall back
to plain-text rendering.

Revision ID: 0021_response_segments
Revises: 0020_fix_audio_recording_urls
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0021_response_segments"
down_revision = "0020_fix_audio_recording_urls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.add_column(sa.Column("response_segments", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.drop_column("response_segments")
