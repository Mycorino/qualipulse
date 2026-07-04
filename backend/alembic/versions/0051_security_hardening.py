"""Security hardening columns on companies:

- token_version — session-revocation counter carried in JWTs ("tv" claim)
- totp_secret / totp_enabled / totp_backup_codes — TOTP two-factor auth
- failed_login_attempts / locked_until — brute-force lockout

Revision ID: 0051_security_hardening
Revises: 0050_ledger_stripe_session_id
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0051_security_hardening"
down_revision = "0050_ledger_stripe_session_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("companies", sa.Column("totp_secret", sa.String(length=64), nullable=True))
    op.add_column(
        "companies",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column("companies", sa.Column("totp_backup_codes", sa.Text(), nullable=True))
    op.add_column(
        "companies",
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("companies", sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "locked_until")
    op.drop_column("companies", "failed_login_attempts")
    op.drop_column("companies", "totp_backup_codes")
    op.drop_column("companies", "totp_enabled")
    op.drop_column("companies", "totp_secret")
    op.drop_column("companies", "token_version")
