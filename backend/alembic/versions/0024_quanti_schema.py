"""Quanti schema — Studies, Surveys, Survey questions, links, responses.

Adds the data layer for the post-design-system quanti track. Eight new
tables plus a nullable `study_id` on `projects` with a same-transaction
backfill: one Study per existing Project.

Future migration (post-Sprint 6 verification) makes `projects.study_id`
non-nullable. Until then, the column stays nullable so existing reads
continue to work without modification — see roadmap risk #10.

Revision ID: 0024_quanti_schema
Revises: 0023_google_oauth
Create Date: 2026-05-08
"""
from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0024_quanti_schema"
down_revision = "0023_google_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── studies ──────────────────────────────────────────────────────────
    op.create_table(
        "studies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )

    # ── study_participants ───────────────────────────────────────────────
    op.create_table(
        "study_participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "study_id",
            sa.String(36),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("magic_token", sa.String(64), unique=True, nullable=True, index=True),
        sa.Column("email_normalized", sa.String(255), nullable=True, index=True),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column(
            "panel_profile_id",
            sa.Integer(),
            sa.ForeignKey("panel_profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── consent_acknowledgments ──────────────────────────────────────────
    op.create_table(
        "consent_acknowledgments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "study_participant_id",
            sa.String(36),
            sa.ForeignKey("study_participants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "study_id",
            sa.String(36),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "accepted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("consent_text_hash", sa.String(64), nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=True),
    )

    # ── surveys ──────────────────────────────────────────────────────────
    op.create_table(
        "surveys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "study_id",
            sa.String(36),
            sa.ForeignKey("studies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "role",
            sa.String(20),
            nullable=False,
            server_default="standalone",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("fielding_started_at", sa.DateTime(), nullable=True),
        sa.Column("fielding_ended_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
    )

    # ── survey_questions ─────────────────────────────────────────────────
    op.create_table(
        "survey_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "survey_id",
            sa.String(36),
            sa.ForeignKey("surveys.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("type", sa.String(20), nullable=False, index=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column(
            "is_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deprecated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_survey_questions_survey_sort",
        "survey_questions",
        ["survey_id", "sort_order"],
    )

    # ── survey_links ─────────────────────────────────────────────────────
    op.create_table(
        "survey_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "survey_id",
            sa.String(36),
            sa.ForeignKey("surveys.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("token", sa.String(64), unique=True, nullable=False, index=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("opens_at", sa.DateTime(), nullable=True),
        sa.Column("closes_at", sa.DateTime(), nullable=True),
        sa.Column("target_n", sa.Integer(), nullable=True),
        sa.Column("response_cap", sa.Integer(), nullable=True),
        sa.Column(
            "is_anonymous", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── survey_responses ─────────────────────────────────────────────────
    op.create_table(
        "survey_responses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "survey_id",
            sa.String(36),
            sa.ForeignKey("surveys.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "company_id",
            sa.String(36),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "study_participant_id",
            sa.String(36),
            sa.ForeignKey("study_participants.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "link_id",
            sa.String(36),
            sa.ForeignKey("survey_links.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("submission_metadata", sa.Text(), nullable=True),
        sa.Column(
            "is_excluded", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("quality_flags", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_survey_responses_company_completed",
        "survey_responses",
        ["company_id", "completed_at"],
    )
    op.create_index(
        "ix_survey_responses_survey_completed",
        "survey_responses",
        ["survey_id", "completed_at"],
    )

    # ── survey_response_answers ──────────────────────────────────────────
    op.create_table(
        "survey_response_answers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "response_id",
            sa.String(36),
            sa.ForeignKey("survey_responses.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "question_id",
            sa.String(36),
            sa.ForeignKey("survey_questions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "answered_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("value_numeric", sa.Float(), nullable=True),
        sa.Column("value_text", sa.Text(), nullable=True),
        sa.Column("value_choice_ids", sa.Text(), nullable=True),
        sa.Column("time_to_answer_ms", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_answers_question_numeric",
        "survey_response_answers",
        ["question_id", "value_numeric"],
    )

    # ── projects.study_id (nullable, with backfill) ───────────────────────
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(
            sa.Column(
                "study_id",
                sa.String(36),
                sa.ForeignKey("studies.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        batch_op.create_index("ix_projects_study_id", ["study_id"])

    # Backfill: one Study per existing Project, same name.
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, company_id, name FROM projects WHERE study_id IS NULL")
    ).fetchall()
    now = datetime.now(timezone.utc)
    for project_id, company_id, name in rows:
        study_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO studies (id, company_id, name, created_at) "
                "VALUES (:id, :company_id, :name, :created_at)"
            ),
            {
                "id": study_id,
                "company_id": company_id,
                "name": name,
                "created_at": now,
            },
        )
        bind.execute(
            sa.text("UPDATE projects SET study_id = :study_id WHERE id = :project_id"),
            {"study_id": study_id, "project_id": project_id},
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_index("ix_projects_study_id")
        batch_op.drop_column("study_id")

    op.drop_index("ix_answers_question_numeric", table_name="survey_response_answers")
    op.drop_table("survey_response_answers")

    op.drop_index(
        "ix_survey_responses_survey_completed", table_name="survey_responses"
    )
    op.drop_index(
        "ix_survey_responses_company_completed", table_name="survey_responses"
    )
    op.drop_table("survey_responses")

    op.drop_table("survey_links")

    op.drop_index("ix_survey_questions_survey_sort", table_name="survey_questions")
    op.drop_table("survey_questions")

    op.drop_table("surveys")
    op.drop_table("consent_acknowledgments")
    op.drop_table("study_participants")
    op.drop_table("studies")
