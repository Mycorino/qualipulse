"""Panel enrichment — profiling question bank + per-panelist answers.

Adds the catalogue (`panel_attributes`), the answer store (`panel_answers`),
and the explicit special-category consent flags on `panel_profiles`. The
catalogue is seeded/synced on startup from services/panel_catalog.py.

Revision ID: 0044_panel_enrichment
Revises: 0043_participant_pref_lang

NOTE: keep revision ids <= 32 chars — alembic_version.version_num is
VARCHAR(32) on Postgres.
"""
from alembic import op
import sqlalchemy as sa


revision = "0044_panel_enrichment"
down_revision = "0043_participant_pref_lang"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "panel_attributes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("category", sa.String(), nullable=False, index=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("options", sa.Text(), nullable=True),
        sa.Column("label_i18n", sa.Text(), nullable=False),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "panel_answers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "profile_id",
            sa.Integer(),
            sa.ForeignKey("panel_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "attribute_id",
            sa.String(),
            sa.ForeignKey("panel_attributes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("profile_id", "attribute_id", name="uq_panel_answer"),
    )
    op.add_column(
        "panel_profiles",
        sa.Column("sensitive_data_consent", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "panel_profiles",
        sa.Column("sensitive_data_consent_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("panel_profiles", "sensitive_data_consent_at")
    op.drop_column("panel_profiles", "sensitive_data_consent")
    op.drop_table("panel_answers")
    op.drop_table("panel_attributes")
