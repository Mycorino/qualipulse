"""Admin operations: audit log table, account suspension columns.

Revision ID: 0040_admin_ops
Revises: 0039_study_readiness
"""
from alembic import op
import sqlalchemy as sa


revision = "0040_admin_ops"
down_revision = "0039_study_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("admin_identity", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("target_company_id", sa.String(36),
                  sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_company_email", sa.String(255), nullable=False),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("is_impersonation", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_admin_audit_log_action", "admin_audit_log", ["action"])
    op.create_index("ix_admin_audit_log_target_company_id", "admin_audit_log", ["target_company_id"])
    op.create_index("ix_admin_audit_log_created_at", "admin_audit_log", ["created_at"])

    op.add_column("companies", sa.Column("suspended_at", sa.DateTime, nullable=True))
    op.add_column("companies", sa.Column("suspension_reason", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "suspension_reason")
    op.drop_column("companies", "suspended_at")
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_target_company_id", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_action", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
