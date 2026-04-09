"""Add preferred_language column to companies table.

Revision ID: 0010_add_preferred_language
Revises: 0009_blog_posts
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa


revision = "0010_add_preferred_language"
down_revision = "0009_blog_posts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column(
            "preferred_language",
            sa.String(5),
            nullable=False,
            server_default="fr",
        ),
    )


def downgrade() -> None:
    op.drop_column("companies", "preferred_language")
