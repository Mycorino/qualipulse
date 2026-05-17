"""Add studies.research_plan — onboarding 3-phase research plan.

Adds a nullable ``research_plan`` TEXT column on ``studies``. Holds the
JSON-serialised 3-phase research plan (screener survey → interviews →
validation survey) generated during onboarding Step 4. Persisted so the
Study page can render the plan as a roadmap after onboarding ends, keeping
Phases 2 and 3 discoverable.

Nullable: only Studies born from the onboarding research-plan flow carry
one. Existing Studies and Studies created via the angle picker stay NULL.

Revision ID: 0028_study_research_plan
Revises: 0027_backfill_orphan_studies
Create Date: 2026-05-17

Note: revision id is 24 chars — well under the VARCHAR(32) limit of
``alembic_version.version_num`` (see migration 0027's note).
"""
from alembic import op
import sqlalchemy as sa


revision = "0028_study_research_plan"
down_revision = "0027_backfill_orphan_studies"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("studies") as batch_op:
        batch_op.add_column(sa.Column("research_plan", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("studies") as batch_op:
        batch_op.drop_column("research_plan")
