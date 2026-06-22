"""Per-language localizations for the research context (consent screen).

Adds projects.research_context_translations (JSON text): {"fr": "<text>", ...}.
Display-only for participants; the canonical projects.research_context stays the
researcher's source of truth.

Revision ID: 0047_research_context_i18n
Revises: 0046_study_name_translations

NOTE: keep revision ids <= 32 chars — alembic_version.version_num is
VARCHAR(32) on Postgres.
"""
from alembic import op
import sqlalchemy as sa


revision = "0047_research_context_i18n"
down_revision = "0046_study_name_translations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("research_context_translations", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("projects", "research_context_translations")
