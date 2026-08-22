"""participant_magic_tokens.reusable — non-burning invite links.

Revision ID: 0069_reusable_magic_token
Revises: 0068_unique_turn_index
Create Date: 2026-08-21

Recontact invites now carry a magic token instead of the generic shared
interview URL, so clicking the invited email proves possession the same way
the verification flow does, with no extra step for the participant. Those
tokens must survive being clicked more than once: the session JWT they issue
lasts 2 hours, and a panelist who opens the invite, steps away, and returns
the next day would otherwise be permanently locked out of their own
invitation with no self-serve way to request another.

Reuse is safe because the token binds to one email and the existing
one-completed-interview-per-email-per-link guard is unchanged, so a
re-clicked or forwarded invite still cannot produce a second interview.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0069_reusable_magic_token"
down_revision = "0068_unique_turn_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "participant_magic_tokens",
        sa.Column(
            "reusable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("participant_magic_tokens", "reusable")
