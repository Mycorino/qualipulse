"""Participant onboarding redesign — per-participant preferred language.

Participants now pick their own interview language (en/fr/de/es/it/pt) on
the landing screen. That choice overrides the study's default language for
the AI interviewer + voice, so we persist it on the participant. We also
store it on the reusable panel profile so future study invites can email
people in their language.

Revision ID: 0043_participant_pref_lang
Revises: 0042_affiliate_fk_indexes

NOTE: keep revision ids <= 32 chars — alembic_version.version_num is
VARCHAR(32) on Postgres, so a longer id fails the version write at runtime
(SQLite doesn't enforce the length, so it only surfaces in production).
"""
from alembic import op
import sqlalchemy as sa


revision = "0043_participant_pref_lang"
down_revision = "0042_affiliate_fk_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "participants",
        sa.Column("preferred_language", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "panel_profiles",
        sa.Column("preferred_language", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("panel_profiles", "preferred_language")
    op.drop_column("participants", "preferred_language")
