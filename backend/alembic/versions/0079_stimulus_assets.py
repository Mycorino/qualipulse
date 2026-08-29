"""stimulus_assets — artefacts shown to participants during an interview.

Revision ID: 0079_stimulus_assets
Revises: 0078_recording_segments
Create Date: 2026-08-29

Concept tests, packaging tests and ad-creative reactions all need something
on the participant's screen at a precise moment. This adds the asset table,
the guide-question attachment that decides when it appears, and a per-turn
stamp recording what was actually on screen when the answer was given.

Both foreign keys are SET NULL: deleting an asset unsticks the picture, it
never deletes a question or a turn.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0079_stimulus_assets"
down_revision = "0078_recording_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stimulus_assets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="image"),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("caption", sa.String(300), nullable=True),
        sa.Column("ai_description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_stimulus_assets_project_id", "stimulus_assets", ["project_id"]
    )

    with op.batch_alter_table("interview_guide_questions") as batch:
        batch.add_column(sa.Column("stimulus_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_guide_question_stimulus",
            "stimulus_assets",
            ["stimulus_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("interview_turns") as batch:
        batch.add_column(sa.Column("stimulus_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_interview_turn_stimulus",
            "stimulus_assets",
            ["stimulus_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch:
        batch.drop_constraint("fk_interview_turn_stimulus", type_="foreignkey")
        batch.drop_column("stimulus_id")

    with op.batch_alter_table("interview_guide_questions") as batch:
        batch.drop_constraint("fk_guide_question_stimulus", type_="foreignkey")
        batch.drop_column("stimulus_id")

    op.drop_index("ix_stimulus_assets_project_id", table_name="stimulus_assets")
    op.drop_table("stimulus_assets")
