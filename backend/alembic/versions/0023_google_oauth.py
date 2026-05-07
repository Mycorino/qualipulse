"""Add google_sub column and make password_hash nullable.

Adds Google Sign-In support. Accounts created via Google OAuth have a
``google_sub`` (Google's stable user id) and no ``password_hash``.
Password-only accounts continue to have ``password_hash`` set and
``google_sub`` null. Linking happens by email match on first Google
sign-in for an existing password account.

Revision ID: 0023_google_oauth
Revises: 0022_credits_system
Create Date: 2026-05-06
"""
from alembic import op
import sqlalchemy as sa


revision = "0023_google_oauth"
down_revision = "0022_credits_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("companies") as batch_op:
        batch_op.add_column(sa.Column("google_sub", sa.String(64), nullable=True))
        batch_op.alter_column("password_hash", existing_type=sa.String(255), nullable=True)
        batch_op.create_index("ix_companies_google_sub", ["google_sub"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("companies") as batch_op:
        batch_op.drop_index("ix_companies_google_sub")
        batch_op.alter_column("password_hash", existing_type=sa.String(255), nullable=False)
        batch_op.drop_column("google_sub")
