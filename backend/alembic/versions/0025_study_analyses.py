"""Study analyses table — Quantified Themes report (Sprint 11).

Parallel to ``project_analyses`` (the existing qualitative analysis cache)
but keyed to a Study. One Study can have many analyses over time; the
v1 UX only surfaces the latest, but the table is versioned so the
"researcher edits a generated theme" loop in a future sprint can keep
both the AI's original and the edited version.

Schema decisions:
  - `report` is a JSON blob whose shape is validated client-side by
    the `QuantifiedThemeReport` Pydantic schema (app/schemas/study.py).
  - `status` is "generating" | "ready" | "failed" — same shape as
    `project_analyses.status` so the frontend polling logic is
    reusable.
  - `error` captures the failure message when status="failed" so the
    Researcher UI can render an honest "we couldn't generate this
    because…" message instead of a generic spinner-of-doom.

Revision ID: 0025_study_analyses
Revises: 0024_quanti_schema
Create Date: 2026-05-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0025_study_analyses"
down_revision = "0024_quanti_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "study_id",
            sa.String(36),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="generating"),
        sa.Column("report", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        # Snapshot of the inputs Claude saw so a future researcher can
        # re-run with the same data + audit what generated a theme.
        sa.Column("inputs_snapshot", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_study_analyses_study_created",
        "study_analyses",
        ["study_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_study_analyses_study_created", table_name="study_analyses")
    op.drop_table("study_analyses")
