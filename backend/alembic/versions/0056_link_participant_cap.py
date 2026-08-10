"""Add interview_links.max_participants.

Optional per-link ceiling on admitted participants. An open shareable
link that leaks (forwarded, posted in a community) otherwise admits
unlimited participants, and every completed interview consumes a credit
from the workspace balance. The cap lets a researcher bound the exposure
per link without deactivating it. NULL = uncapped (existing behaviour).

Revision ID: 0056_link_participant_cap
Revises: 0055_drop_max_active_projects
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0056_link_participant_cap"
down_revision = "0055_drop_max_active_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_links",
        sa.Column("max_participants", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("interview_links", "max_participants")
