"""Interview engine v2 — pacing, planning, fatigue, and turn classification.

Adds three columns to ``participants``:
- ``talk_seconds``       — cumulative Whisper-reported seconds of participant audio
- ``interview_plan``     — JSON blob of pre-flight per-question budgets
- ``fatigue_state``      — rolling fatigue label (low | medium | high | null)

Adds one column to ``interview_turns``:
- ``turn_kind``          — explicit classification (main, follow_up, reframe,
                           clarification, skip_skip, closing)

Revision ID: 0019_interview_engine_v2
Revises: 0018_transcript_translation
Create Date: 2026-04-25
"""
from alembic import op
import sqlalchemy as sa


revision = "0019_interview_engine_v2"
down_revision = "0018_transcript_translation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("participants") as batch_op:
        batch_op.add_column(
            sa.Column(
                "talk_seconds",
                sa.Float(),
                nullable=False,
                server_default=sa.text("0.0"),
            )
        )
        batch_op.add_column(sa.Column("interview_plan", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("fatigue_state", sa.String(length=16), nullable=True))

    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.add_column(
            sa.Column(
                "turn_kind",
                sa.String(length=16),
                nullable=False,
                server_default="main",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.drop_column("turn_kind")

    with op.batch_alter_table("participants") as batch_op:
        batch_op.drop_column("fatigue_state")
        batch_op.drop_column("interview_plan")
        batch_op.drop_column("talk_seconds")
