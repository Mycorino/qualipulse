"""Add researcher features: transcript editing, guide annotation, coding, memos, analysis filters.

Revision ID: 0001_researcher_features
Revises:
Create Date: 2026-04-02
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_researcher_features"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── interview_turns: transcript editing ──────────────────────────────────
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.add_column(sa.Column("manually_edited", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column("edited_at", sa.DateTime(), nullable=True))

    # ── project_analyses: filter tracking ───────────────────────────────────
    with op.batch_alter_table("project_analyses") as batch_op:
        batch_op.add_column(sa.Column("filters", sa.Text(), nullable=True))

    # ── interview_guide_questions: researcher annotations ───────────────────
    with op.batch_alter_table("interview_guide_questions") as batch_op:
        batch_op.add_column(sa.Column("researcher_notes", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("deprecated_at", sa.DateTime(), nullable=True))

    # ── participants: demographic attributes ─────────────────────────────────
    with op.batch_alter_table("participants") as batch_op:
        batch_op.add_column(sa.Column("age_range", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("profession", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("country", sa.String(100), nullable=True))

    # ── manual_codes ─────────────────────────────────────────────────────────
    op.create_table(
        "manual_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("color", sa.String(7), nullable=False, server_default="#6366f1"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # ── quote_tags ────────────────────────────────────────────────────────────
    op.create_table(
        "quote_tags",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("turn_id", sa.String(36), sa.ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manual_code_id", sa.String(36), sa.ForeignKey("manual_codes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("selected_text", sa.Text(), nullable=False),
        sa.Column("start_index", sa.Integer(), nullable=False),
        sa.Column("end_index", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    # ── project_memos ─────────────────────────────────────────────────────────
    op.create_table(
        "project_memos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False, server_default="general"),
        sa.Column("linked_key", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("project_memos")
    op.drop_table("quote_tags")
    op.drop_table("manual_codes")

    with op.batch_alter_table("participants") as batch_op:
        batch_op.drop_column("country")
        batch_op.drop_column("profession")
        batch_op.drop_column("age_range")

    with op.batch_alter_table("interview_guide_questions") as batch_op:
        batch_op.drop_column("deprecated_at")
        batch_op.drop_column("researcher_notes")

    with op.batch_alter_table("project_analyses") as batch_op:
        batch_op.drop_column("filters")

    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.drop_column("edited_at")
        batch_op.drop_column("manually_edited")
