"""projects.profile_before_interview — where profiling sits in the flow.

Revision ID: 0072_profile_position
Revises: 0071_participant_review
Create Date: 2026-08-23

The socio-demographic questionnaire was moved after the interview to stop
7-11 taps of profiling standing between a participant and the first
question. That is the right default, but it is not right for every study:
some researchers need the profile to interpret or segment answers, and some
screen on it, so for them it has to come first even at the cost of
drop-off.

Per-study flag rather than a global choice. Default false keeps the
current post-interview behaviour for every existing study.

Keep revision ids at or under 32 characters (see 0063 for why).
"""
import sqlalchemy as sa
from alembic import op

revision = "0072_profile_position"
down_revision = "0071_participant_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "profile_before_interview",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "profile_before_interview")
