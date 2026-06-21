"""Per-language localizations for the study name.

Adds projects.name_translations (JSON text): {"fr": "<name>", ...}. Display-only
for participants; the canonical projects.name stays the researcher's source of
truth + identity.

Revision ID: 0046_study_name_translations
Revises: 0045_screening_translations

NOTE: keep revision ids <= 32 chars — alembic_version.version_num is
VARCHAR(32) on Postgres.
"""
from alembic import op
import sqlalchemy as sa


revision = "0046_study_name_translations"
down_revision = "0045_screening_translations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("name_translations", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "name_translations")
