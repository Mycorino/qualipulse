"""Create ai_usage_log table for tracking Claude, TTS, and STT costs.

Revision ID: 0006_ai_usage_log
Revises: 0005_enhanced_onboarding
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_ai_usage_log"
down_revision = "0005_enhanced_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_log",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "company_id",
            sa.Integer(),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("operation", sa.String(), nullable=False, index=True),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("characters", sa.Integer(), nullable=True),
        sa.Column("audio_seconds", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, default=0.0),
        sa.Column("created_at", sa.DateTime(), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("ai_usage_log")
