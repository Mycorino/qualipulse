"""Workspace-level participant-branding defaults on companies.

companies.branding_defaults — JSON dict of Project branding fields,
prefilled into every new study (the study's Setup tab keeps the final say).

Revision ID: 0054_company_branding_defaults
Revises: 0053_project_branding
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0054_company_branding_defaults"
down_revision = "0053_project_branding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("branding_defaults", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "branding_defaults")
