"""Realtime beta: per-turn answer spans for researcher parity.

The sideband knows when each answer started (speech detected) and ended
(transcript committed). Stamping that span onto the turn lets a
completion-time job slice the session recording into per-turn answer clips
and Whisper them for sentence segments — filling audio_recording_url and
response_segments exactly like classic interviews, so the researcher
transcript view is identical for both transports.

Revision ID: 0080_turn_answer_span
Revises: 0079_stimulus_assets
"""

import sqlalchemy as sa
from alembic import op

revision = "0080_turn_answer_span"
down_revision = "0079_stimulus_assets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_turns",
        sa.Column("answer_offset_seconds", sa.Float(), nullable=True),
    )
    op.add_column(
        "interview_turns",
        sa.Column("answer_end_seconds", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_turns", "answer_end_seconds")
    op.drop_column("interview_turns", "answer_offset_seconds")
