"""Add warmup_enabled column to projects.

PF-3: per-project toggle for the AI moderator's opening warm-up turn.
Default True so existing projects pick up the new behaviour, with a
researcher-facing toggle in project settings to opt out.

Revision ID: 0019_warmup_enabled
Revises: 0018_transcript_translation
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0019_warmup_enabled"
down_revision = "0018_transcript_translation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column(
                "warmup_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("warmup_enabled")
