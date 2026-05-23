"""Add Company.first_response_email_sent_at — idempotency guard for the
W3.2 "your first response is in" lifecycle email.

Revision ID: 0031_first_response_email
Revises: 0030_copilot_convo_scope
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0031_first_response_email"
down_revision = "0030_copilot_convo_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "first_response_email_sent_at",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "first_response_email_sent_at")
