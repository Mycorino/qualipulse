"""Merge the two parallel 0064 heads.

0064_company_utm (PR #359, marketing attribution) and
0064_email_suppression (PR #355) both landed on top of
0063_merge_0062_heads from PRs that were open at the same time, leaving
the graph with two heads. `alembic upgrade head` then refuses to run,
start.sh falls back to create_all(), and the container exits 255: that
is what failed the 2026-08-21 deploy of 081fa7e.

Each PR verified a single head against its own branch and was correct at
the time. The second head only appears once both are on main, so this
class of break is invisible until the merge, and the check that catches
it has to run against origin/main rather than the feature branch.

Keep revision ids at or under 32 characters (see 0063 for why).

Revision ID: 0065_merge_0064_heads
Revises: 0064_company_utm, 0064_email_suppression
Create Date: 2026-08-21
"""

revision = "0065_merge_0064_heads"
down_revision = ("0064_company_utm", "0064_email_suppression")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
