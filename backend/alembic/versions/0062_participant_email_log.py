"""Add participant_email_log for interview reminder emails.

Per-participant analogue of email_send_log: one row per
(participant x event), unique-constrained so the reminder pass of
/admin/scheduled-emails/run is idempotent across replayed cron firings.

Revision ID: 0062_participant_email_log
Revises: 0061_participant_screening_answers
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0062_participant_email_log"
down_revision = "0061_participant_screening_answers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participant_email_log",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "participant_id",
            sa.String(length=36),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(length=50), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "participant_id", "event", name="uq_participant_email_log_event"
        ),
    )
    op.create_index(
        "ix_participant_email_log_participant_id",
        "participant_email_log",
        ["participant_id"],
    )
    op.create_index(
        "ix_participant_email_log_event", "participant_email_log", ["event"]
    )


def downgrade() -> None:
    op.drop_index("ix_participant_email_log_event", table_name="participant_email_log")
    op.drop_index(
        "ix_participant_email_log_participant_id",
        table_name="participant_email_log",
    )
    op.drop_table("participant_email_log")
