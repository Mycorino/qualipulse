"""Wave E — research plan + step tables.

A ResearchPlan is the multi-step research program a researcher commits
to at the end of onboarding. Each ResearchPlanStep is one method in the
plan. Projects gain optional `plan_id` + `plan_step_index` so the UI
can show "Study 1 of 3 in your ticket-purchase plan."

Revision ID: 0037_research_plan
Revises: 0036_onboarding_personalisation_cache
"""
from alembic import op
import sqlalchemy as sa


revision = "0037_research_plan"
down_revision = "0036_onboarding_personalisation_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_plans",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(),
            sa.ForeignKey("companies.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("decision_to_inform", sa.Text(), nullable=True),
        sa.Column("timeline", sa.String(), nullable=True),
        sa.Column("success_criteria", sa.Text(), nullable=True),
        sa.Column("target_customer_description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "research_plan_steps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(),
            sa.ForeignKey("research_plans.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("deliverable", sa.Text(), nullable=True),
        sa.Column("n_participants", sa.Integer(), nullable=True),
        sa.Column("duration_weeks", sa.Integer(), nullable=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "plan_id", "order_index", name="uq_plan_step_order"
        ),
    )


def downgrade() -> None:
    op.drop_table("research_plan_steps")
    op.drop_table("research_plans")
