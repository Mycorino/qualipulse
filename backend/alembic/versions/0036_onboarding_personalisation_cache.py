"""Cache Haiku-generated personalised greeting + starter suggestions on Company.

Adds two pairs of nullable columns:
  - welcome_greeting_text / welcome_greeting_at
  - starter_suggestions_json / starter_suggestions_at

Each pair stores the cached generation text and the timestamp it was
generated. The endpoint regenerates when older than 24h or empty.

Revision ID: 0036_onboarding_personalisation_cache
Revises: 0035
"""
from alembic import op
import sqlalchemy as sa


revision = "0036_onboarding_personalisation_cache"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("welcome_greeting_text", sa.Text(), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("welcome_greeting_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("starter_suggestions_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("starter_suggestions_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "starter_suggestions_at")
    op.drop_column("companies", "starter_suggestions_json")
    op.drop_column("companies", "welcome_greeting_at")
    op.drop_column("companies", "welcome_greeting_text")
