"""Add email_verification_tokens table and APP_BASE_URL support.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_email_verification"
down_revision = "0002_iterative_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(64), unique=True, nullable=False),
        sa.Column("used", sa.Boolean, default=False, nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_email_verification_tokens_token", "email_verification_tokens", ["token"])


def downgrade() -> None:
    op.drop_index("ix_email_verification_tokens_token", "email_verification_tokens")
    op.drop_table("email_verification_tokens")
