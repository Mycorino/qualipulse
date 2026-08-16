"""Add affiliates.preferred_language.

Captured from the UI language at apply time; drives the language of the
affiliate lifecycle emails (application received / approved / rejected /
magic-link login / conversion / payout). Affiliates have no Company row,
so the language must live on the Affiliate itself.

Revision ID: 0059_affiliate_language
Revises: 0058_tag_suggestions
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0059_affiliate_language"
down_revision = "0058_tag_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "affiliates",
        sa.Column("preferred_language", sa.String(5), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("affiliates", "preferred_language")
