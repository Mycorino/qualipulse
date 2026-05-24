"""V4 paywall — sticky has_ever_paid flag on Company.

Free workspaces see the first 3 completed transcripts and the rest are
paywall-locked. Paid (or ever-paid) workspaces see everything. This
column is the sticky boolean that survives subscription cancellation,
so ex-customers don't lose access to historical data when they pause.

Backfill: any company whose subscription_status has ever been
``active``, ``canceled``, ``past_due`` (i.e. they billed at some point)
gets ``has_ever_paid=True``.

Revision ID: 0034_paywall_visibility
Revises: 0033_onboarding_v2
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa


revision = "0034_paywall_visibility"
down_revision = "0033_onboarding_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "has_ever_paid",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "companies",
        sa.Column(
            "free_preview_full_email_sent_at",
            sa.DateTime(),
            nullable=True,
        ),
    )
    # Backfill — anyone who's been past 'trialing' state has paid.
    op.execute(
        """
        UPDATE companies
        SET has_ever_paid = 1
        WHERE subscription_status IN ('active', 'canceled', 'past_due')
        """
    )


def downgrade() -> None:
    op.drop_column("companies", "free_preview_full_email_sent_at")
    op.drop_column("companies", "has_ever_paid")
