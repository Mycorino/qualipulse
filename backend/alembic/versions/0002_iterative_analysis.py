"""Add iterative analysis: researcher_context, version_label, parent_version_id, analysis_theme_annotations.

Revision ID: 0002_iterative_analysis
Revises: 0001_researcher_features
Create Date: 2026-04-04
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_iterative_analysis"
down_revision = "0001_researcher_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── project_analyses: new fields ─────────────────────────────────────────
    with op.batch_alter_table("project_analyses") as batch_op:
        batch_op.add_column(sa.Column("researcher_context", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("version_label", sa.String(20), nullable=False, server_default="ai_discovery"))
        batch_op.add_column(sa.Column("parent_version_id", sa.String(36), nullable=True))

    # ── analysis_theme_annotations ────────────────────────────────────────────
    op.create_table(
        "analysis_theme_annotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("analysis_id", sa.String(36), sa.ForeignKey("project_analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("theme_title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("researcher_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("analysis_id", "theme_title", name="uq_annotation_analysis_theme"),
    )


def downgrade() -> None:
    op.drop_table("analysis_theme_annotations")

    with op.batch_alter_table("project_analyses") as batch_op:
        batch_op.drop_column("parent_version_id")
        batch_op.drop_column("version_label")
        batch_op.drop_column("researcher_context")
