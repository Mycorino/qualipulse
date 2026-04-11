"""Onboarding audit: add qualification + business context fields.

Adds the fields we need to both (a) qualify leads at signup time for the
sales pipeline and (b) ground AI analysis in the researcher's business
context.

Company-level (applies to every project the company runs):
- value_proposition        # one-sentence product pitch
- primary_competitors      # comma-separated list
- product_stage            # idea / mvp / growth / scale
- customer_type            # b2c / b2b / b2b2c / internal
- interviews_per_month_target  # qualification signal
- current_tool             # qualification signal (what they use today)
- decision_role            # qualification signal (buyer / influencer / user)
- goals_classification     # Claude-classified bucket(s) for goals_freeform

Project-level (study-specific, overrides company context if set):
- decision_to_inform        # what decision this study will unblock
- target_customer_description  # who we're talking to in this study

Revision ID: 0014_onboarding_audit_fields
Revises: 0013_add_demo_project_flag
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa


revision = "0014_onboarding_audit_fields"
down_revision = "0013_add_demo_project_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Company business context
    op.add_column("companies", sa.Column("value_proposition", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("primary_competitors", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("product_stage", sa.String(length=30), nullable=True))
    op.add_column("companies", sa.Column("customer_type", sa.String(length=30), nullable=True))

    # Company qualification signals
    op.add_column(
        "companies",
        sa.Column("interviews_per_month_target", sa.String(length=30), nullable=True),
    )
    op.add_column("companies", sa.Column("current_tool", sa.String(length=100), nullable=True))
    op.add_column("companies", sa.Column("decision_role", sa.String(length=50), nullable=True))
    op.add_column(
        "companies",
        sa.Column("goals_classification", sa.String(length=200), nullable=True),
    )

    # Project study grounding
    op.add_column("projects", sa.Column("decision_to_inform", sa.Text(), nullable=True))
    op.add_column(
        "projects",
        sa.Column("target_customer_description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "target_customer_description")
    op.drop_column("projects", "decision_to_inform")
    op.drop_column("companies", "goals_classification")
    op.drop_column("companies", "decision_role")
    op.drop_column("companies", "current_tool")
    op.drop_column("companies", "interviews_per_month_target")
    op.drop_column("companies", "customer_type")
    op.drop_column("companies", "product_stage")
    op.drop_column("companies", "primary_competitors")
    op.drop_column("companies", "value_proposition")
