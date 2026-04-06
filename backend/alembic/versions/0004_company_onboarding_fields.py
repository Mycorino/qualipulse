"""Add onboarding profile fields to companies table.

Revision ID: 0004_company_onboarding_fields
Revises: 0003_email_verification
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_company_onboarding_fields"
down_revision = "0003_email_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("company_size", sa.String(50), nullable=True))
    op.add_column("companies", sa.Column("role", sa.String(100), nullable=True))
    op.add_column("companies", sa.Column("industry", sa.String(100), nullable=True))
    op.add_column("companies", sa.Column("use_case", sa.String(100), nullable=True))
    op.add_column("companies", sa.Column("onboarding_completed", sa.Boolean, server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("companies", "onboarding_completed")
    op.drop_column("companies", "use_case")
    op.drop_column("companies", "industry")
    op.drop_column("companies", "role")
    op.drop_column("companies", "company_size")
