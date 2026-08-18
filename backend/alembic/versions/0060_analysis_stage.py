"""Add project_analyses.stage + stage_detail.

The analysis run becomes a staged pipeline (auto_tagging → preparing →
synthesizing → verifying) and the frontend polls these columns to render
a labelled progress bar instead of an opaque spinner.

Revision ID: 0060_analysis_stage
Revises: 0059_affiliate_language
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "0060_analysis_stage"
down_revision = "0059_affiliate_language"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("project_analyses", sa.Column("stage", sa.String(20), nullable=True))
    op.add_column("project_analyses", sa.Column("stage_detail", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("project_analyses", "stage_detail")
    op.drop_column("project_analyses", "stage")
