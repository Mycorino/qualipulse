"""Current priority re-prompt fields on Company.

Adds two columns that let us ask the researcher once a month "what's top of
mind for you right now?" and keep the answer next to them as they work.

- current_priority         # short free-form text the researcher types
- current_priority_updated_at   # when they last answered (used by the UI to
                                 # decide whether to re-prompt after ~30 days)

Revision ID: 0015_current_priority
Revises: 0014_onboarding_audit_fields
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_current_priority"
down_revision = "0014_onboarding_audit_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("current_priority", sa.Text(), nullable=True))
    op.add_column(
        "companies",
        sa.Column("current_priority_updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "current_priority_updated_at")
    op.drop_column("companies", "current_priority")
