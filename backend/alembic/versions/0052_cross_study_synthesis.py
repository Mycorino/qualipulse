"""cross_study_syntheses — decision memos synthesised across several Studies.

Revision ID: 0052_cross_study_synthesis
Revises: 0051_security_hardening
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0052_cross_study_synthesis"
down_revision = "0051_security_hardening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cross_study_syntheses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(length=36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("decision_question", sa.Text(), nullable=True),
        sa.Column("study_ids", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="generating"),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="en"),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_cross_study_syntheses_company_id", "cross_study_syntheses", ["company_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_cross_study_syntheses_company_id", table_name="cross_study_syntheses")
    op.drop_table("cross_study_syntheses")
