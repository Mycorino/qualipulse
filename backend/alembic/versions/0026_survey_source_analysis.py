"""Validation surveys — link survey to source analysis.

Adds a nullable ``source_analysis_id`` FK on ``surveys`` pointing at
``study_analyses``. Set when a Survey is generated from an analysis as
a validation micro-survey (Sprint 14, "closing the loop": quantify →
explain → validate).

Nullable because standalone + screener surveys never have a source
analysis. SET NULL on delete so deleting an analysis doesn't cascade
into the survey it spawned — the validation survey may have collected
responses we want to keep.

Revision ID: 0026_survey_source_analysis
Revises: 0025_study_analyses
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0026_survey_source_analysis"
down_revision = "0025_study_analyses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add a plain column first, then attach the FK via batch.create_foreign_key
    # with an explicit constraint name — SQLite batch mode rebuilds the table
    # and refuses to handle an anonymous FK during the rebuild.
    with op.batch_alter_table("surveys") as batch_op:
        batch_op.add_column(
            sa.Column("source_analysis_id", sa.String(36), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_surveys_source_analysis_id",
            "study_analyses",
            ["source_analysis_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_surveys_source_analysis", ["source_analysis_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("surveys") as batch_op:
        batch_op.drop_index("ix_surveys_source_analysis")
        batch_op.drop_constraint(
            "fk_surveys_source_analysis_id", type_="foreignkey"
        )
        batch_op.drop_column("source_analysis_id")
