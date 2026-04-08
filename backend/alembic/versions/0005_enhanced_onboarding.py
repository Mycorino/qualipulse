"""Add enhanced onboarding fields to companies table.

Revision ID: 0005_enhanced_onboarding
Revises: 0004_company_onboarding_fields
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_enhanced_onboarding"
down_revision = "0004_company_onboarding_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("website_url", sa.String(500), nullable=True))
    op.add_column("companies", sa.Column("business_summary", sa.Text, nullable=True))
    op.add_column("companies", sa.Column("research_experience", sa.String(20), nullable=True))
    op.add_column("companies", sa.Column("primary_region", sa.String(30), nullable=True))
    op.add_column("companies", sa.Column("goals_freeform", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "goals_freeform")
    op.drop_column("companies", "primary_region")
    op.drop_column("companies", "research_experience")
    op.drop_column("companies", "business_summary")
    op.drop_column("companies", "website_url")
