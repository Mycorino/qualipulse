"""Participant review state + project incentive text.

Revision ID: 0071_participant_review
Revises: 0068_unique_turn_index
Create Date: 2026-08-22

Researcher tools for compensated studies: `projects.incentive_text` is the
opt-in switch (shown to participants verbatim); `participants.review_status`
(pending / approved / rejected) gates what counts as research data, with
`review_note`, `reviewed_at` and `reward_sent_at` for the review and reward
queues. Existing rows backfill to "approved" via the server default so no
historical interview changes state.
"""
import sqlalchemy as sa
from alembic import op

revision = "0071_participant_review"
down_revision = "0070_magic_token_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("participants") as batch_op:
        batch_op.add_column(
            sa.Column(
                "review_status",
                sa.String(20),
                nullable=False,
                server_default="approved",
            )
        )
        batch_op.add_column(sa.Column("reviewed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("review_note", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("reward_sent_at", sa.DateTime(), nullable=True))
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("incentive_text", sa.String(300), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("incentive_text")
    with op.batch_alter_table("participants") as batch_op:
        batch_op.drop_column("reward_sent_at")
        batch_op.drop_column("review_note")
        batch_op.drop_column("reviewed_at")
        batch_op.drop_column("review_status")
