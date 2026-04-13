"""Add quality assessment columns to participants.

Adds five nullable columns for storing AI quality assessment results:
- quality_summary       — 2-3 sentence overall assessment
- quality_strengths     — JSON list of strengths
- quality_issues        — JSON list of issues
- avg_response_words    — average word count per response
- short_answer_pct      — percentage of responses under 10 words

Revision ID: 0017_quality_assessment
Revises: 0016_onboarding_redesign
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa


revision = "0017_quality_assessment"
down_revision = "0016_onboarding_redesign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("participants") as batch_op:
        batch_op.add_column(sa.Column("quality_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("quality_strengths", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("quality_issues", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("avg_response_words", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("short_answer_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("participants") as batch_op:
        batch_op.drop_column("short_answer_pct")
        batch_op.drop_column("avg_response_words")
        batch_op.drop_column("quality_issues")
        batch_op.drop_column("quality_strengths")
        batch_op.drop_column("quality_summary")
