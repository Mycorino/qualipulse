"""Drop plans.max_active_projects.

The active-project cap was never enforced for credits-based plans
(usage is gated by interview credits) and legacy tiers read their cap
from feature_gates.TIER_LIMITS, so the column was pure metadata. The
limit is removed from the plan catalogue, the /billing/plans response,
and the pricing UI — this drops the now-unused column.

Revision ID: 0055_drop_max_active_projects
Revises: 0054_company_branding_defaults
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0055_drop_max_active_projects"
down_revision = "0054_company_branding_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("plans", "max_active_projects")


def downgrade() -> None:
    op.add_column("plans", sa.Column("max_active_projects", sa.Integer(), nullable=True))
