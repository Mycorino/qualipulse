"""Per-language localizations for screening questions.

Adds screening_questions.translations (JSON text): {"fr": {"question": str,
"options": [str]}, ...}. Display-only; the canonical question/options stay the
source of truth + the disqualification gate's stable identity.

Revision ID: 0045_screening_translations
Revises: 0044_panel_enrichment

NOTE: keep revision ids <= 32 chars — alembic_version.version_num is
VARCHAR(32) on Postgres.
"""
from alembic import op
import sqlalchemy as sa


revision = "0045_screening_translations"
down_revision = "0044_panel_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "screening_questions",
        sa.Column("translations", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("screening_questions", "translations")
