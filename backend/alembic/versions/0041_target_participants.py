"""Add target_participants column to projects.

The completed-interview target a researcher is aiming for in this round
(or the Research Copilot's recommended sample size). Advisory — drives
the Setup sample-size guidance, not a hard gate.

Revision ID: 0041_target_participants
Revises: 0040_admin_ops
"""
from alembic import op
import sqlalchemy as sa


revision = "0041_target_participants"
down_revision = "0040_admin_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("target_participants", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "target_participants")
