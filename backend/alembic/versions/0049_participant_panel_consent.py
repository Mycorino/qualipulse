"""Add participants.panel_consent.

Denormalised recontact flag copied from PanelProfile.panel_consent (matched
by email) when the interview completes or the panel profile is saved. Lets
researchers filter/export participants who agreed to follow-ups without a
join onto panel_profiles. NULL = unknown (pre-feature rows).

Revision ID: 0049_participant_panel_consent
Revises: 0048_transcript_cleanup
Create Date: 2026-07-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0049_participant_panel_consent"
down_revision = "0048_transcript_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("participants") as batch_op:
        batch_op.add_column(sa.Column("panel_consent", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("participants") as batch_op:
        batch_op.drop_column("panel_consent")
