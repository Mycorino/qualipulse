"""Add slack_webhook_url column to companies table.

Revision ID: 0011_add_slack_webhook_url
Revises: 0010_add_preferred_language
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa


revision = "0011_add_slack_webhook_url"
down_revision = "0010_add_preferred_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("slack_webhook_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "slack_webhook_url")
