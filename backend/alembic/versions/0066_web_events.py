"""Add web_events: anonymous marketing-site funnel events.

Backs the admin Traffic tab. Cloud Logging keeps the same events for 30
days; this table keeps them for good, which is what makes "did the
channel we spent on in March convert by June?" answerable at all.

Revision ID: 0066_web_events
Revises: 0065_merge_0064_heads
Create Date: 2026-08-21
"""
from alembic import op
import sqlalchemy as sa

revision = "0066_web_events"
down_revision = "0065_merge_0064_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("location", sa.String(64), nullable=True),
        sa.Column("path", sa.String(200), nullable=True),
        sa.Column("visitor", sa.String(32), nullable=True),
        sa.Column("referrer", sa.String(300), nullable=True),
        sa.Column("utm_source", sa.String(100), nullable=True),
        sa.Column("utm_medium", sa.String(100), nullable=True),
        sa.Column("utm_campaign", sa.String(100), nullable=True),
        sa.Column("lang", sa.String(5), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_web_events_id", "web_events", ["id"])
    op.create_index("ix_web_events_event", "web_events", ["event"])
    op.create_index("ix_web_events_visitor", "web_events", ["visitor"])
    op.create_index("ix_web_events_utm_source", "web_events", ["utm_source"])
    op.create_index("ix_web_events_created_at", "web_events", ["created_at"])
    op.create_index("ix_web_events_event_created", "web_events", ["event", "created_at"])


def downgrade() -> None:
    op.drop_table("web_events")
