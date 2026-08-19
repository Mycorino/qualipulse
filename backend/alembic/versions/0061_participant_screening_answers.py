"""Add participants.screening_answers.

Snapshot of the options a qualified participant clicked through in the
screener (JSON list of {question_id, question, answer}). Previously the
answers were checked for disqualification and thrown away; now they feed
the analysis prompt headers, segment filters, and the heatmap.

Revision ID: 0061_participant_screening_answers
Revises: 0060_analysis_stage
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0061_participant_screening_answers"
down_revision = "0060_analysis_stage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("participants", sa.Column("screening_answers", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("participants", "screening_answers")
