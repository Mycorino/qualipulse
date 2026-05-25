"""Add study_readiness column to companies.

Captures whether the user has a concrete study in mind or is still
evaluating — helps the onboarding copilot tailor its first question.

Revision ID: 0039_study_readiness
Revises: 0038_demo_opening_question_cache
"""
from alembic import op
import sqlalchemy as sa


revision = "0039_study_readiness"
down_revision = "0038_demo_opening_question_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("study_readiness", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "study_readiness")
