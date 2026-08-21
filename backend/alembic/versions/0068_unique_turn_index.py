"""Unique (participant_id, turn_index) on interview_turns.

Revision ID: 0068_unique_turn_index
Revises: 0067_merge_0065_0066
Create Date: 2026-08-21

Backs out the per-participant `SELECT ... FOR UPDATE` added alongside
turn-index reconciliation (#363): in production it hung a genuine /respond
request for the full 300s Cloud Run timeout with zero forward progress (no
Whisper/Claude/TTS call was ever even attempted), most likely a lock wait
against Neon's serverless Postgres with no `lock_timeout` set, so a
contended lock blocks indefinitely rather than failing fast. An unbounded
wait on the request path is unacceptable regardless of the exact cause.

This constraint gives the same protection the row lock was meant to (two
racing writers can never both insert a turn at the same index) without ever
blocking: the loser gets an immediate IntegrityError to catch and recover
from, not a wait.
"""
from alembic import op

revision = "0068_unique_turn_index"
down_revision = "0067_merge_0065_0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    dupes = conn.exec_driver_sql(
        """
        SELECT participant_id, turn_index, COUNT(*)
        FROM interview_turns
        GROUP BY participant_id, turn_index
        HAVING COUNT(*) > 1
        LIMIT 5
        """
    ).fetchall()
    if dupes:
        raise RuntimeError(
            "Refusing to add uq_turn_participant_index: existing duplicate "
            f"(participant_id, turn_index) rows found, e.g. {dupes}. "
            "Resolve these manually (keep the turn with a response, or the "
            "earliest by created_at) before re-running this migration."
        )
    # batch_alter_table: SQLite has no ALTER TABLE ADD CONSTRAINT (it copies
    # the table under the hood instead); this keeps the migration portable to
    # local/dev SQLite instead of only working on production Postgres.
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.create_unique_constraint(
            "uq_turn_participant_index", ["participant_id", "turn_index"]
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.drop_constraint("uq_turn_participant_index", type_="unique")
