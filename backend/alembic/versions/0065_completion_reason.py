"""Participant.completion_reason (natural / participant_finished / ...).

Revision ID: 0065_completion_reason
Revises: 0064_email_suppression
Create Date: 2026-08-21
"""
import sqlalchemy as sa
from alembic import op

revision = "0065_completion_reason"
down_revision = "0064_email_suppression"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("completion_reason", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("participants", "completion_reason")
