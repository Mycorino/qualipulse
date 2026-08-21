"""Email suppression list (bounces, spam reports, unsubscribes).

Revision ID: 0064_email_suppression
Revises: 0063_merge_0062_heads
Create Date: 2026-08-20

Revision id kept under 32 chars — ``alembic_version.version_num`` was the
default VARCHAR(32) until the 0063 drift fix widened it, and an over-long
id silently rolls the whole migration back (see the 2026-08-19 incident).
"""
import sqlalchemy as sa
from alembic import op

revision = "0064_email_suppression"
down_revision = "0063_merge_0062_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_suppressions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="sendgrid_webhook"),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_email_suppressions_email",
        "email_suppressions",
        ["email"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_email_suppressions_email", table_name="email_suppressions")
    op.drop_table("email_suppressions")
