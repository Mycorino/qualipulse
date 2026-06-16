"""Participant onboarding redesign — per-participant preferred language.

Participants now pick their own interview language (en/fr/de/es/it/pt) on
the landing screen. That choice overrides the study's default language for
the AI interviewer + voice, so we persist it on the participant. We also
store it on the reusable panel profile so future study invites can email
people in their language.

Revision ID: 0043_participant_preferred_language
Revises: 0042_affiliate_fk_indexes
"""
from alembic import op
import sqlalchemy as sa


revision = "0043_participant_preferred_language"
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
