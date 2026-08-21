"""Merge the 0065_completion_reason and 0066_web_events heads.

Fourth occurrence of the same shape (0062, 0064, now this). Two PRs open
at the same time each add a migration, each verifies a single head
against its own branch, and the second head only comes into existence
once both are on main. Build 12e58894 for 272707c failed on it.

The CI guard added alongside this revision should be the last word on
it: actions/checkout on a pull_request event checks out the *merge*
commit, so `alembic heads` there sees what main will look like after the
merge rather than what the branch looks like before it.

Keep revision ids at or under 32 characters (see 0063 for why).

Revision ID: 0067_merge_0065_0066
Revises: 0065_completion_reason, 0066_web_events
Create Date: 2026-08-21
"""

revision = "0067_merge_0065_0066"
down_revision = ("0065_completion_reason", "0066_web_events")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
