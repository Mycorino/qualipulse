"""Research Copilot — per-workspace memory.

The Research Copilot is the in-context AI assistant. It keeps a small,
workspace-scoped memory of durable facts (research preferences, recurring
audiences, house style) so it stays consistent across studies and
surfaces. One row per Company; the copilot reads it into every system
prompt and appends to it via its `remember` tool.

Revision ID: 0028_copilot_memory
Revises: 0027_backfill_orphan_studies
Create Date: 2026-05-17

Note: the revision id is kept under 32 chars — see 0027 for why.
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "0028_copilot_memory"
down_revision = "0027_backfill_orphan_studies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "copilot_memory",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime(), nullable=False, default=datetime.utcnow),
    )
    # One memory row per workspace.
    op.create_index(
        "ix_copilot_memory_company", "copilot_memory", ["company_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_copilot_memory_company", table_name="copilot_memory")
    op.drop_table("copilot_memory")
