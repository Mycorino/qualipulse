"""Add blog_posts table.

Revision ID: 0009_blog_posts
Revises: 0008_affiliate_program
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_blog_posts"
down_revision = "0008_affiliate_program"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blog_posts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("subtitle", sa.String(500), nullable=True),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("excerpt", sa.String(500), nullable=True),
        sa.Column("cover_image_url", sa.String(500), nullable=True),
        sa.Column("meta_title", sa.String(255), nullable=True),
        sa.Column("meta_description", sa.String(500), nullable=True),
        sa.Column("og_image_url", sa.String(500), nullable=True),
        sa.Column("author_name", sa.String(255), nullable=False, server_default="QualiPulse Team"),
        sa.Column("tags", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft", index=True),
        sa.Column("published_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("blog_posts")
