"""Research Copilot — generalise conversations to scoped instruments.

``copilot_conversations`` was keyed by ``survey_id``. The copilot is
moving onto the interview guide (a Project) and other surfaces, so the
table is re-keyed by ``(scope_kind, scope_id)`` — the same polymorphic
scheme already used by ``copilot_memory``.

The table shipped in 0029 the same day, so this drops and recreates it
rather than running an in-place column swap. Persisted chat threads are
ephemeral (hours old), so losing the handful created since 0029 is
acceptable and far simpler than a SQLite batch rebuild of a FK column.

Revision ID: 0030_copilot_convo_scope
Revises: 0029_copilot_scope_convo
Create Date: 2026-05-17
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


revision = "0030_copilot_convo_scope"
down_revision = "0029_copilot_scope_convo"
branch_labels = None
depends_on = None


def _create_scoped() -> None:
    op.create_table(
        "copilot_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_kind", sa.String(16), nullable=False),
        sa.Column("scope_id", sa.String(36), nullable=False),
        sa.Column("thread", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(), nullable=False, default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime(), nullable=False, default=datetime.utcnow),
    )
    op.create_index(
        "ix_copilot_conversations_scope",
        "copilot_conversations",
        ["scope_kind", "scope_id"],
        unique=True,
    )


def upgrade() -> None:
    op.drop_index(
        "ix_copilot_conversations_survey", table_name="copilot_conversations"
    )
    op.drop_table("copilot_conversations")
    _create_scoped()


def downgrade() -> None:
    op.drop_index(
        "ix_copilot_conversations_scope", table_name="copilot_conversations"
    )
    op.drop_table("copilot_conversations")
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
