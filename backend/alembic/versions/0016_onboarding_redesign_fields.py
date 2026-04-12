"""Onboarding redesign — personal identity + recap fields on Company.

Adds five columns for the new onboarding flow:
- first_name, last_name        — split name for personalised greetings
- occupation_description       — free-form "what do you actually do day-to-day"
- selected_use_cases           — JSON-serialised list of research topics chosen
- onboarding_recap             — Claude-generated strategy brief shown at the end

Revision ID: 0016_onboarding_redesign
Revises: 0015_current_priority
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa


revision = "0016_onboarding_redesign"
down_revision = "0015_current_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(sa.Column("first_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("last_name", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("occupation_description", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("selected_use_cases", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("onboarding_recap", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_column("onboarding_recap")
        batch_op.drop_column("selected_use_cases")
        batch_op.drop_column("occupation_description")
        batch_op.drop_column("last_name")
        batch_op.drop_column("first_name")
