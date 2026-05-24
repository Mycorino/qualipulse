"""Add version column to copilot_conversations for optimistic concurrency."""

from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "copilot_conversations",
        sa.Column("version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade():
    op.drop_column("copilot_conversations", "version")
