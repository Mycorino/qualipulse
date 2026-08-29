"""Realtime beta: per-connection recording segments.

One realtime interview can span several browser connections (resume after a
break, a device change, a second tab). Each connection records its own audio,
and the single participants.session_recording_url slot made those uploads
overwrite and delete each other — losing audio and orphaning turn offsets.
Segments give every connection its own row: uploads only ever replace their
own segment's file, and turns are stamped with the segment their offset
belongs to.

Revision ID: 0078_recording_segments
Revises: 0077_turn_audio_offset
"""

import sqlalchemy as sa
from alembic import op

revision = "0078_recording_segments"
down_revision = "0077_turn_audio_offset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "realtime_recording_segments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "participant_id",
            sa.String(length=36),
            sa.ForeignKey("participants.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("segment_key", sa.String(length=40), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "participant_id", "segment_key", name="uq_recording_segment_per_participant"
        ),
    )
    op.add_column(
        "interview_turns",
        sa.Column("audio_segment_key", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_turns", "audio_segment_key")
    op.drop_table("realtime_recording_segments")
