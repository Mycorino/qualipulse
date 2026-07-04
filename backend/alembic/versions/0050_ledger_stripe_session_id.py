"""Add credit_ledger.stripe_session_id — structured idempotency key for
Stripe checkout grants and refund revocations (replaces JSON LIKE matching
on event_metadata for new rows).

Revision ID: 0050_ledger_stripe_session_id
Revises: 0049_participant_panel_consent
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0050_ledger_stripe_session_id"
down_revision = "0049_participant_panel_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "credit_ledger",
        sa.Column("stripe_session_id", sa.String(length=100), nullable=True),
    )
    op.create_index(
        "ix_credit_ledger_stripe_session_id",
        "credit_ledger",
        ["stripe_session_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_credit_ledger_stripe_session_id", table_name="credit_ledger")
    op.drop_column("credit_ledger", "stripe_session_id")
