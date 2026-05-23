"""Onboarding V2 — strategic-context capture during the welcome chat.

Adds three Project fields (decision_to_inform already exists; we add
timeline + success_criteria) and one Company field (referral_source —
current_tool already exists). These are the WHY + HOW we were missing
in V1: the decision the researcher needs to make, when it's due, how
they'll know we helped, and how they found us.

Revision ID: 0033_onboarding_v2
Revises: 0032_email_send_log
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0033_onboarding_v2"
down_revision = "0032_email_send_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("timeline", sa.String(100), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("success_criteria", sa.Text(), nullable=True),
    )
    op.add_column(
        "companies",
        sa.Column("referral_source", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "referral_source")
    op.drop_column("projects", "success_criteria")
    op.drop_column("projects", "timeline")
