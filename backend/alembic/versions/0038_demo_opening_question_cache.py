"""Cache the Haiku-generated participant-demo opening question.

Same pattern as the welcome-greeting / starter-suggestions cache:
the question is personalised per researcher, expires after 24h, and
falls back to a static i18n string when the Haiku call hasn't yet
landed or the wizard was skipped.

Revision ID: 0038_demo_opening_question_cache
Revises: 0037_research_plan
"""
from alembic import op
import sqlalchemy as sa


revision = "0038_demo_opening_question_cache"
down_revision = "0037_research_plan"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("demo_opening_question_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("demo_opening_question_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "demo_opening_question_at")
    op.drop_column("companies", "demo_opening_question_text")
