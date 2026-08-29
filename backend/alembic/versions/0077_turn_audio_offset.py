"""interview_turns.audio_offset_seconds — per-turn position in the
realtime session recording.

Revision ID: 0077_turn_audio_offset
Revises: 0076_beta_features
Create Date: 2026-08-27

Realtime interviews record one continuous session file instead of per-turn
clips. This column stores, per turn, how many seconds into that recording
the turn's question begins, so the researcher can jump the session player
to any turn ("audio for each sequence"). Stamped live by the sideband
bridge; NULL for classic turns and pre-feature realtime interviews.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0077_turn_audio_offset"
down_revision = "0076_beta_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_turns",
        sa.Column("audio_offset_seconds", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_turns", "audio_offset_seconds")
