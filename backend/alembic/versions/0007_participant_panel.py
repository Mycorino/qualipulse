"""Add participant panel and email verification tables.

Revision ID: 0007_participant_panel
Revises: 0006_ai_usage_log
Create Date: 2026-04-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect as sa_inspect

revision = "0007_participant_panel"
down_revision = "0006_ai_usage_log"
branch_labels = None
depends_on = None

INTEREST_TAGS = [
    "Technology", "Travel", "Health & Fitness", "Finance", "Gaming",
    "Fashion", "Food & Cooking", "Parenting", "Sports", "Environment",
    "Music", "Art & Design", "Books", "Home & Garden", "Pets",
]

BEHAVIOR_TAGS = [
    "Remote worker", "Frequent business traveler", "Early adopter", "Brand loyal",
    "Price sensitive", "Online-first shopper", "Manages a team",
    "Decision maker", "Startup environment",
]


def _table_exists(conn, table_name: str) -> bool:
    insp = sa_inspect(conn)
    return table_name in insp.get_table_names()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    insp = sa_inspect(conn)
    return any(c["name"] == column_name for c in insp.get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()

    # panel_profiles
    if not _table_exists(bind, "panel_profiles"):
        op.create_table(
            "panel_profiles",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("email", sa.String(), unique=True, nullable=False, index=True),
            sa.Column("first_name", sa.String(), nullable=True),
            sa.Column("age_range", sa.String(), nullable=True),
            sa.Column("gender", sa.String(), nullable=True),
            sa.Column("country", sa.String(), nullable=True),
            sa.Column("city", sa.String(), nullable=True),
            sa.Column("education", sa.String(), nullable=True),
            sa.Column("employment_status", sa.String(), nullable=True),
            sa.Column("job_function", sa.String(), nullable=True),
            sa.Column("seniority", sa.String(), nullable=True),
            sa.Column("industry", sa.String(), nullable=True),
            sa.Column("company_size", sa.String(), nullable=True),
            sa.Column("panel_consent", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("consent_at", sa.DateTime(), nullable=True),
            sa.Column("consent_interview_token", sa.String(), nullable=True),
            sa.Column("interviews_completed", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_active", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    # panel_tags
    if not _table_exists(bind, "panel_tags"):
        op.create_table(
            "panel_tags",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("name", sa.String(), unique=True, nullable=False),
            sa.Column("category", sa.String(), nullable=False),
        )

    # panel_profile_tags (many-to-many)
    if not _table_exists(bind, "panel_profile_tags"):
        op.create_table(
            "panel_profile_tags",
            sa.Column("profile_id", sa.Integer(), sa.ForeignKey("panel_profiles.id", ondelete="CASCADE")),
            sa.Column("tag_id", sa.Integer(), sa.ForeignKey("panel_tags.id", ondelete="CASCADE")),
        )

    # participant_magic_tokens
    if not _table_exists(bind, "participant_magic_tokens"):
        op.create_table(
            "participant_magic_tokens",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(), nullable=False, index=True),
            sa.Column("token", sa.String(), unique=True, nullable=False, index=True),
            sa.Column("interview_link_token", sa.String(), nullable=False),
            sa.Column("used", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    # Add columns to existing tables (idempotent)
    if not _column_exists(bind, "projects", "panel_collection_enabled"):
        op.add_column("projects", sa.Column("panel_collection_enabled", sa.Boolean(), nullable=False, server_default="1"))

    if not _column_exists(bind, "participants", "email_verified"):
        op.add_column("participants", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="0"))

    # Seed panel tags (only if empty)
    count = bind.execute(sa.text("SELECT COUNT(*) FROM panel_tags")).scalar()
    if count == 0:
        panel_tags_table = sa.table(
            "panel_tags",
            sa.column("name", sa.String),
            sa.column("category", sa.String),
        )
        op.bulk_insert(
            panel_tags_table,
            [{"name": tag, "category": "interest"} for tag in INTEREST_TAGS]
            + [{"name": tag, "category": "behavior"} for tag in BEHAVIOR_TAGS],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "participants", "email_verified"):
        op.drop_column("participants", "email_verified")
    if _column_exists(bind, "projects", "panel_collection_enabled"):
        op.drop_column("projects", "panel_collection_enabled")
    op.drop_table("panel_profile_tags")
    op.drop_table("participant_magic_tokens")
    op.drop_table("panel_tags")
    op.drop_table("panel_profiles")
