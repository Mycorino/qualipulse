"""Add affiliate program tables.

Revision ID: 0008_affiliate_program
Revises: 0007_participant_panel
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_affiliate_program"
down_revision = "0007_participant_panel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # affiliates table
    op.create_table(
        "affiliates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("code", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("how_they_found_us", sa.Text, nullable=True),
        sa.Column("commission_pct", sa.Float, nullable=False, server_default="20.0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payout_threshold", sa.Float, nullable=False, server_default="50.0"),
        sa.Column("total_earned", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("total_paid", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("approved_at", sa.DateTime, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
    )

    # affiliate_referrals table
    op.create_table(
        "affiliate_referrals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("affiliate_id", sa.String(36), sa.ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("referred_company_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("signed_up_at", sa.DateTime, nullable=False),
        sa.Column("converted_at", sa.DateTime, nullable=True),
        sa.Column("commission_amount", sa.Float, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="signed_up"),
    )

    # affiliate_payouts table
    op.create_table(
        "affiliate_payouts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("affiliate_id", sa.String(36), sa.ForeignKey("affiliates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Float, nullable=False),
        sa.Column("paid_at", sa.DateTime, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("affiliate_payouts")
    op.drop_table("affiliate_referrals")
    op.drop_table("affiliates")
