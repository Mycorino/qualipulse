"""Backfill orphaned projects into Studies.

Migration 0024 added ``projects.study_id`` and backfilled every project
that existed *at that time*. But until Sprint 15, no project-creation
path set ``study_id`` — so any project created between 0024 and Sprint
15 has ``study_id IS NULL``.

After the Sprint 15 IA flip (dashboard → Studies list), an orphaned
project would be invisible. This migration adopts each one into a fresh
Study named after the project — identical to the 0024 backfill logic.

Idempotent: only touches rows where ``study_id IS NULL``. Safe to
re-run; no-ops once every project has a Study.

Revision ID: 0027_backfill_orphan_studies
Revises: 0026_survey_source_analysis
Create Date: 2026-05-17

Note: the revision id is kept to 28 chars. Alembic stores
``alembic_version.version_num`` as ``VARCHAR(32)``, so a longer id fails
to stamp on Postgres with StringDataRightTruncation — which is exactly
how the original ``0027_backfill_orphan_project_studies`` (36 chars)
broke production deploys.
"""
from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0027_backfill_orphan_studies"
down_revision = "0026_survey_source_analysis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, company_id, name FROM projects WHERE study_id IS NULL"
        )
    ).fetchall()
    now = datetime.now(timezone.utc)
    for project_id, company_id, name in rows:
        study_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO studies (id, company_id, name, created_at) "
                "VALUES (:id, :company_id, :name, :created_at)"
            ),
            {
                "id": study_id,
                "company_id": company_id,
                "name": name,
                "created_at": now,
            },
        )
        bind.execute(
            sa.text("UPDATE projects SET study_id = :study_id WHERE id = :project_id"),
            {"study_id": study_id, "project_id": project_id},
        )


def downgrade() -> None:
    # No-op: we can't reliably tell which Studies this migration created
    # vs. which were authored by users. Leaving the data in place on
    # downgrade is the safe choice — orphaning projects again would be
    # worse than a few extra Study rows.
    pass
