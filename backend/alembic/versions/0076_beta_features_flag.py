"""companies.beta_features_enabled — account opt-in for beta features.

Revision ID: 0076_beta_features
Revises: 0075_realtime_beta
Create Date: 2026-08-27

Beta surfaces (today the realtime live-voice interview mode) stay hidden
unless the workspace explicitly opts in from Account > Profile. Studies
resolve the flag through their owning company, so it is workspace-scoped.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0076_beta_features"
down_revision = "0075_realtime_beta"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "beta_features_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "beta_features_enabled")
