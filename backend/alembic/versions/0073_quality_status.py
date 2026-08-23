"""participants.quality_status — did the AI quality pass actually succeed?

Revision ID: 0073_quality_status
Revises: 0072_profile_position
Create Date: 2026-08-23

The Responses panel had no way to tell a failed assessment from one still in
flight, because the only signal it could read was quality_summary being
empty, and quality_label is no help: the API falls back to a word-count
heuristic for it, so it is populated even when the model call crashed. The
panel therefore announced that the evaluation had "finished" with no summary
written, when in fact the reply had been truncated by the token cap and the
JSON parse had thrown.

NULL means never attempted or still running, which is the correct reading for
every existing row: assessments that already succeeded carry a summary, and
the panel checks that first.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0073_quality_status"
down_revision = "0072_profile_position"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("quality_status", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("participants", "quality_status")
