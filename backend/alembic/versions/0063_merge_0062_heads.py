"""Merge the two parallel 0062 heads.

0062_participant_email_log and 0062_study_invites both landed on top of
0061_participant_screening_answers from parallel PRs, leaving the graph
with two heads — which makes `alembic upgrade head` refuse to run. This
empty merge revision joins them back into a single lineage.

Keep revision ids at or under 32 characters: alembic_version.version_num
is VARCHAR(32) by default, and the 34-char id of 0061 is what broke the
2026-08-19 production deploy (start.sh now widens the column, but short
ids stay the rule).

Revision ID: 0063_merge_0062_heads
Revises: 0062_participant_email_log, 0062_study_invites
Create Date: 2026-08-19
"""

revision = "0063_merge_0062_heads"
down_revision = ("0062_participant_email_log", "0062_study_invites")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
