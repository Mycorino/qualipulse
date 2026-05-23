"""Wave 3B — append-only email_send_log for scheduled lifecycle emails.

One row per (company × event). The unique constraint on
(company_id, event) makes the /admin/scheduled-emails/run runner
idempotent: a duplicate cron firing in the same window trips the
constraint instead of sending again.

Revision ID: 0032_email_send_log
Revises: 0031_first_response_email
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa


revision = "0032_email_send_log"
down_revision = "0031_first_response_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_send_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(50), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "company_id", "event", name="uq_email_send_log_company_event"
        ),
    )
    op.create_index(
        "ix_email_send_log_company_id",
        "email_send_log",
        ["company_id"],
    )
    op.create_index(
        "ix_email_send_log_event",
        "email_send_log",
        ["event"],
    )


def downgrade() -> None:
    op.drop_index("ix_email_send_log_event", table_name="email_send_log")
    op.drop_index("ix_email_send_log_company_id", table_name="email_send_log")
    op.drop_table("email_send_log")
