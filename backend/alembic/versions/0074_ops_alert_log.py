"""ops_alert_log — idempotency keys for team-facing operational alerts.

Revision ID: 0074_ops_alert_log
Revises: 0073_quality_status
Create Date: 2026-08-23

AI provider spend alerts have no Company to hang off, so they cannot reuse
email_send_log. This table gives them the same insert-then-send idempotency:
the unique alert_key encodes the alert and its window, so an hourly cron that
fires twice (or two Cloud Run instances hitting the same threshold at once)
sends one message, not two.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0074_ops_alert_log"
down_revision = "0073_quality_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ops_alert_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("alert_key", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_ops_alert_log_alert_key", "ops_alert_log", ["alert_key"], unique=True
    )
    op.create_index("ix_ops_alert_log_kind", "ops_alert_log", ["kind"])
    op.create_index("ix_ops_alert_log_created_at", "ops_alert_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ops_alert_log_created_at", table_name="ops_alert_log")
    op.drop_index("ix_ops_alert_log_kind", table_name="ops_alert_log")
    op.drop_index("ix_ops_alert_log_alert_key", table_name="ops_alert_log")
    op.drop_table("ops_alert_log")
