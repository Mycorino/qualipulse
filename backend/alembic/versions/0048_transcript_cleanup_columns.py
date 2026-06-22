"""Add transcript ASR-cleanup columns.

Adds a sense-check cache to interview_turns:
- cleaned_response  — Haiku-corrected response text (obvious STT errors fixed
                      using study context). Original response_transcript is
                      never overwritten.
- cleaned_at        — when the cleanup pass ran (also the idempotency marker)

Revision ID: 0048_transcript_cleanup
Revises: 0047_research_context_i18n
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa


revision = "0048_transcript_cleanup"
down_revision = "0047_research_context_i18n"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.add_column(sa.Column("cleaned_response", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("cleaned_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.drop_column("cleaned_at")
        batch_op.drop_column("cleaned_response")
