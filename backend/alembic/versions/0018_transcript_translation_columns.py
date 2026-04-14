"""Add transcript translation columns.

Adds translation cache columns to interview_turns:
- translated_response          — Claude-translated response text
- translated_question          — Claude-translated question text
- translation_language         — target language code (e.g. "fr")
- translation_source_language  — detected source language code

Adds a flag to quote_tags:
- tagged_from_translation      — True if researcher selected from translated view

Revision ID: 0018_transcript_translation
Revises: 0017_quality_assessment
Create Date: 2026-04-14
"""
from alembic import op
import sqlalchemy as sa


revision = "0018_transcript_translation"
down_revision = "0017_quality_assessment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.add_column(sa.Column("translated_response", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("translated_question", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("translation_language", sa.String(length=5), nullable=True))
        batch_op.add_column(sa.Column("translation_source_language", sa.String(length=5), nullable=True))

    with op.batch_alter_table("quote_tags") as batch_op:
        batch_op.add_column(
            sa.Column(
                "tagged_from_translation",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("quote_tags") as batch_op:
        batch_op.drop_column("tagged_from_translation")

    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.drop_column("translation_source_language")
        batch_op.drop_column("translation_language")
        batch_op.drop_column("translated_question")
        batch_op.drop_column("translated_response")
