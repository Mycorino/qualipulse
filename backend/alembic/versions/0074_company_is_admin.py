"""companies.is_admin — named staff accounts for /admin.

Revision ID: 0074_company_is_admin
Revises: 0073_quality_status
Create Date: 2026-08-23

The admin panel used to be opened by one shared secret with a self-declared
name for the audit log. Staff now sign in with their own account; this flag
marks which accounts may open an admin session (plus mandatory TOTP, see
services/admin_auth.py). Never set through the API: scripts/grant_admin.py.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0074_company_is_admin"
down_revision = "0073_quality_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("companies", "is_admin")
