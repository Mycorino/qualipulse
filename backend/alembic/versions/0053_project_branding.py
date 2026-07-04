"""Per-project participant-facing branding:

- branding_mode — "standard" | "branded" | "anonymous" identity policy
- brand_primary_color — hex accent applied to the interview page (branded mode)
- brand_font — curated font-stack key (branded mode)

Revision ID: 0053_project_branding
Revises: 0052_cross_study_synthesis
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0053_project_branding"
down_revision = "0052_cross_study_synthesis"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "branding_mode",
            sa.String(length=20),
            nullable=False,
            server_default="standard",
        ),
    )
    op.add_column(
        "projects", sa.Column("brand_primary_color", sa.String(length=7), nullable=True)
    )
    op.add_column("projects", sa.Column("brand_font", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "brand_font")
    op.drop_column("projects", "brand_primary_color")
    op.drop_column("projects", "branding_mode")
