"""realtime interview beta — per-study transport flag + session recording.

Revision ID: 0075_realtime_beta
Revises: 0074_ops_alert_log
Create Date: 2026-08-26

projects.interview_mode routes the participant flow: "classic" (default,
the record → Whisper → Claude → TTS loop) or "realtime_beta" (live voice
over the OpenAI Realtime API with Claude still deciding every turn via the
sideband bridge). participants.session_recording_url stores the browser's
parallel full-session capture for realtime interviews, since that mode has
no per-turn uploads.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0075_realtime_beta"
down_revision = "0074_ops_alert_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "interview_mode",
            sa.String(20),
            nullable=False,
            server_default="classic",
        ),
    )
    op.add_column(
        "participants",
        sa.Column("session_recording_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("participants", "session_recording_url")
    op.drop_column("projects", "interview_mode")
