"""Add study_invites — recontact invitations to consented panelists.

One row per (project, email) invitation. Funnel status is derived by
joining participants on (project_id, lower(email)); the table itself is
append-only. The unique constraint prevents double-inviting the same
person to the same study.

Revision ID: 0062_study_invites
Revises: 0061_participant_screening_answers
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0062_study_invites"
down_revision = "0061_participant_screening_answers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_invites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("company_id", sa.String(36), nullable=False),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("panel_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column("sent_by", sa.String(36), nullable=True),
        sa.Column("sent_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("project_id", "email", name="uq_invite_per_project_email"),
    )
    op.create_index("ix_study_invites_project_id", "study_invites", ["project_id"])
    op.create_index("ix_study_invites_company_id", "study_invites", ["company_id"])
    op.create_index("ix_study_invites_email", "study_invites", ["email"])
    op.create_index("ix_study_invites_sent_at", "study_invites", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_study_invites_sent_at", table_name="study_invites")
    op.drop_index("ix_study_invites_email", table_name="study_invites")
    op.drop_index("ix_study_invites_company_id", table_name="study_invites")
    op.drop_index("ix_study_invites_project_id", table_name="study_invites")
    op.drop_table("study_invites")
