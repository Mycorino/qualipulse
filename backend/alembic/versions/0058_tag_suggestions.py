"""Add tag_suggestions (AI-suggested quote tags awaiting review).

AI-suggested tags are quarantined from the researcher's codebook: a
suggestion only becomes a real QuoteTag (and, for proposed new codes, a
ManualCode) when the researcher accepts it. Offsets map to the raw
response_transcript, same convention as quote_tags.

Revision ID: 0058_tag_suggestions
Revises: 0057_interview_digest
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0058_tag_suggestions"
down_revision = "0057_interview_digest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tag_suggestions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "participant_id",
            sa.String(36),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "turn_id",
            sa.String(36),
            sa.ForeignKey("interview_turns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "manual_code_id",
            sa.String(36),
            sa.ForeignKey("manual_codes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("proposed_code_name", sa.String(100), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column("start_index", sa.Integer(), nullable=False),
        sa.Column("end_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_tag_suggestions_participant_id", "tag_suggestions", ["participant_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_tag_suggestions_participant_id", table_name="tag_suggestions")
    op.drop_table("tag_suggestions")
