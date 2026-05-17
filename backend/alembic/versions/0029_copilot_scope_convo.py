"""Research Copilot — scoped memory + conversation persistence.

Two changes:

1. Generalises ``copilot_memory`` from one-row-per-company to *scoped*
   memory keyed by ``(scope_kind, scope_id)`` — company / study / survey.
   The copilot stacks every applicable tier into its system prompt, so a
   fact learned about a Study is shared by all its surveys, and a
   workspace fact is shared everywhere.

2. Adds ``copilot_conversations`` — one persisted chat thread per survey.
   The panel reloads it on mount, so the conversation resumes instead of
   being lost the moment the researcher navigates away.

Revision ID: 0029_copilot_scope_convo
Revises: 0028_copilot_memory
Create Date: 2026-05-17
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "0029_copilot_scope_convo"
down_revision = "0028_copilot_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Scoped memory — add (scope_kind, scope_id), backfill existing rows
    #    as company-scoped, then swap the unique index.
    op.add_column(
        "copilot_memory",
        sa.Column(
            "scope_kind", sa.String(16), nullable=False, server_default="company"
        ),
    )
    op.add_column(
        "copilot_memory", sa.Column("scope_id", sa.String(36), nullable=True)
    )
    op.execute("UPDATE copilot_memory SET scope_id = company_id")
    op.drop_index("ix_copilot_memory_company", table_name="copilot_memory")
    op.create_index(
        "ix_copilot_memory_scope",
        "copilot_memory",
        ["scope_kind", "scope_id"],
        unique=True,
    )

    # 2. Conversation persistence — one chat thread per survey.
    op.create_table(
        "copilot_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "survey_id",
            sa.String(36),
            sa.ForeignKey("surveys.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thread", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime(), nullable=False, default=datetime.utcnow),
    )
    op.create_index(
        "ix_copilot_conversations_survey",
        "copilot_conversations",
        ["survey_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_copilot_conversations_survey", table_name="copilot_conversations"
    )
    op.drop_table("copilot_conversations")
    op.drop_index("ix_copilot_memory_scope", table_name="copilot_memory")
    op.create_index(
        "ix_copilot_memory_company", "copilot_memory", ["company_id"], unique=True
    )
    op.drop_column("copilot_memory", "scope_id")
    op.drop_column("copilot_memory", "scope_kind")
