"""Add missing FK indexes on affiliate_referrals + affiliate_payouts.

Both tables join on affiliate_id (per-affiliate referral lists, payout
history) but the FK columns were unindexed — those queries table-scanned.
Add a btree index to each.

Revision ID: 0042_affiliate_fk_indexes
Revises: 0041_target_participants
"""
from alembic import op


revision = "0042_affiliate_fk_indexes"
down_revision = "0041_target_participants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_affiliate_referrals_affiliate_id",
        "affiliate_referrals",
        ["affiliate_id"],
    )
    op.create_index(
        "ix_affiliate_payouts_affiliate_id",
        "affiliate_payouts",
        ["affiliate_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_affiliate_payouts_affiliate_id", table_name="affiliate_payouts")
    op.drop_index("ix_affiliate_referrals_affiliate_id", table_name="affiliate_referrals")
