"""participant_magic_tokens.code / code_attempts — email OTP.

Revision ID: 0070_magic_token_code
Revises: 0069_reusable_magic_token
Create Date: 2026-08-22

The verification email now carries a six-digit code alongside the magic
link. Tapping the link from a mail app opens the study in that app's in-app
browser, where MediaRecorder is frequently unavailable (the participant UI
already ships an interstitial for exactly this) and the original tab's
sessionStorage is gone, which for a voice interview is fatal rather than
merely annoying. Typing the code instead keeps the participant in the tab
they started in, on the device and browser where they already granted mic
permission.

``code_attempts`` backs the brute-force cap: six digits is only a million
combinations, so the code is only safe with a hard per-token attempt limit.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0070_magic_token_code"
down_revision = "0069_reusable_magic_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "participant_magic_tokens", sa.Column("code", sa.String(length=6), nullable=True)
    )
    op.add_column(
        "participant_magic_tokens",
        sa.Column("code_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_participant_magic_tokens_code", "participant_magic_tokens", ["code"]
    )


def downgrade() -> None:
    op.drop_index("ix_participant_magic_tokens_code", table_name="participant_magic_tokens")
    op.drop_column("participant_magic_tokens", "code_attempts")
    op.drop_column("participant_magic_tokens", "code")
