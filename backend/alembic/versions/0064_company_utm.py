"""Add first-touch marketing attribution to companies.

``referral_source`` is self-declared during onboarding ("how did you hear
about us?"). These three columns are *measured* instead: the SPA captures
the utm_* trio from the landing URL on first touch and carries it through
both the password and Google signup paths, so a ``paid_converted`` event
can be traced back to the channel that produced it.

Revision ID: 0064_company_utm
Revises: 0063_merge_0062_heads
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0064_company_utm"
down_revision = "0063_merge_0062_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("utm_source", sa.String(100), nullable=True))
    op.add_column("companies", sa.Column("utm_medium", sa.String(100), nullable=True))
    op.add_column("companies", sa.Column("utm_campaign", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "utm_campaign")
    op.drop_column("companies", "utm_medium")
    op.drop_column("companies", "utm_source")
