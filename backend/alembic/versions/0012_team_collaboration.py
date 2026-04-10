"""Add workspace_members and workspace_invitations for team collaboration.

Revision ID: 0012_team_collaboration
Revises: 0011_add_slack_webhook_url
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa


revision = "0012_team_collaboration"
down_revision = "0011_add_slack_webhook_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "member_company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="editor"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.UniqueConstraint(
            "workspace_company_id", "member_company_id", name="uq_workspace_member"
        ),
    )
    op.create_index(
        "ix_workspace_members_workspace_company_id",
        "workspace_members",
        ["workspace_company_id"],
    )
    op.create_index(
        "ix_workspace_members_member_company_id",
        "workspace_members",
        ["member_company_id"],
    )

    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="editor"),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "invited_by_company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("accepted", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("accepted_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "ix_workspace_invitations_workspace_company_id",
        "workspace_invitations",
        ["workspace_company_id"],
    )
    op.create_index(
        "ix_workspace_invitations_email", "workspace_invitations", ["email"]
    )
    op.create_index(
        "ix_workspace_invitations_token", "workspace_invitations", ["token"]
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_invitations_token", table_name="workspace_invitations")
    op.drop_index("ix_workspace_invitations_email", table_name="workspace_invitations")
    op.drop_index(
        "ix_workspace_invitations_workspace_company_id",
        table_name="workspace_invitations",
    )
    op.drop_table("workspace_invitations")
    op.drop_index(
        "ix_workspace_members_member_company_id", table_name="workspace_members"
    )
    op.drop_index(
        "ix_workspace_members_workspace_company_id", table_name="workspace_members"
    )
    op.drop_table("workspace_members")
