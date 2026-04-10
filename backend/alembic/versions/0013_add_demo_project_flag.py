"""Add is_demo flag to projects so showcase projects are excluded from quotas.

Also adds demo_seeded_at to companies so we only auto-seed once per account
(idempotent onboarding).

Revision ID: 0013_add_demo_project_flag
Revises: 0012_team_collaboration
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa


revision = "0013_add_demo_project_flag"
down_revision = "0012_team_collaboration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "is_demo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "companies",
        sa.Column("demo_seeded_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "demo_seeded_at")
    op.drop_column("projects", "is_demo")
