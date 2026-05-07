"""Survey + SurveyQuestion + SurveyLink + SurveyResponse + SurveyResponseAnswer.

The quantitative half of the Study. Surveys live under a Study and share
participant identity with any sibling Project (interview track) via
StudyParticipant — that's what powers the Screener Bridge wedge.

See docs/quanti-roadmap.md sections 1.1, 1.4, and 1.5 for decisions.
"""

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Question types supported in v1. MaxDiff, conjoint, sliders, ranking are
# explicitly killed (see roadmap section 5).
QUESTION_TYPES = ("likert", "mc_single", "mc_multi", "nps", "open_text", "short_text")


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized for cheap quota counting (see roadmap 1.6).
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Survey roles — drives where it surfaces in the mixed-methods report:
    # "screener" appears at the top of the wedge flow; "validation" appears
    # post-interview; "standalone" is a normal study survey.
    role: Mapped[str] = mapped_column(
        String(20), default="standalone", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="draft", nullable=False
    )  # "draft" | "live" | "closed"
    # Methodology metadata. Auto-set from first/last completed_at unless the
    # researcher overrides; powers MethodologyBox on every dashboard view.
    fielding_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fielding_ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    study = relationship("Study", back_populates="surveys")
    company = relationship("Company")
    questions = relationship(
        "SurveyQuestion",
        back_populates="survey",
        cascade="all, delete-orphan",
        order_by="SurveyQuestion.sort_order",
    )
    links = relationship(
        "SurveyLink", back_populates="survey", cascade="all, delete-orphan"
    )
    responses = relationship(
        "SurveyResponse", back_populates="survey", cascade="all, delete-orphan"
    )


class SurveyQuestion(Base):
    """Polymorphic single-table question model.

    `type` is one of QUESTION_TYPES; `config` is a JSON blob whose shape
    depends on `type`. Validated by Pydantic schemas in app/schemas/survey.py.
    Reorder is a single UPDATE on `sort_order`. Deletion is soft via
    `deprecated_at` because answers FK to question_id and we don't drop them.
    """

    __tablename__ = "survey_questions"
    __table_args__ = (
        Index("ix_survey_questions_survey_sort", "survey_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    survey_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Type-specific config — see schemas for shape per type.
    config: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    survey = relationship("Survey", back_populates="questions")
    answers = relationship(
        "SurveyResponseAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
    )

    @property
    def config_dict(self) -> dict:
        try:
            return json.loads(self.config) if self.config else {}
        except (json.JSONDecodeError, TypeError):
            return {}


class SurveyLink(Base):
    """Public collection link for a Survey.

    Token uniqueness is enforced within this table. App-level inserts also
    check `interview_links.token` for collision (see roadmap risk #2). The
    32-byte URL-safe token space makes accidental collision negligible.
    """

    __tablename__ = "survey_links"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    survey_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closes_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    target_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Default False per roadmap Decision 3 — anonymity kills the screener bridge,
    # so we default to identified and require explicit opt-in for anonymous.
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    survey = relationship("Survey", back_populates="links")
    responses = relationship("SurveyResponse", back_populates="link")


class SurveyResponse(Base):
    """One row per submission attempt, completed or partial.

    `completed_at IS NULL` is a real state — partial responses count toward
    the trustworthiness contract (completion rate is part of MethodologyBox).

    `company_id` is denormalized for cheap quota counting per period.
    `study_participant_id` carries identity across instruments (the wedge).
    """

    __tablename__ = "survey_responses"
    __table_args__ = (
        Index("ix_survey_responses_company_completed", "company_id", "completed_at"),
        Index("ix_survey_responses_survey_completed", "survey_id", "completed_at"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    survey_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("surveys.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    study_participant_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("study_participants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    link_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("survey_links.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submission_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Quality flagging surfaces. Defaults: not excluded, no flags.
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quality_flags: Mapped[str | None] = mapped_column(Text, nullable=True)

    survey = relationship("Survey", back_populates="responses")
    company = relationship("Company")
    study_participant = relationship(
        "StudyParticipant", back_populates="survey_responses"
    )
    link = relationship("SurveyLink", back_populates="responses")
    answers = relationship(
        "SurveyResponseAnswer",
        back_populates="response",
        cascade="all, delete-orphan",
    )


class SurveyResponseAnswer(Base):
    """One row per answered question within a SurveyResponse.

    Three value columns by design (see roadmap 1.5):
      - value_numeric: Likert (1..N), NPS (0..10).
      - value_text: open_text, short_text.
      - value_choice_ids: JSON array of choice IDs for mc_single / mc_multi.

    Type-specific aggregations are trivial without polymorphism gymnastics.
    """

    __tablename__ = "survey_response_answers"
    __table_args__ = (
        Index("ix_answers_question_numeric", "question_id", "value_numeric"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    response_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("survey_responses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("survey_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    answered_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON array of choice IDs for mc_single / mc_multi.
    value_choice_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    # For speeder detection at quality-flag time.
    time_to_answer_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    response = relationship("SurveyResponse", back_populates="answers")
    question = relationship("SurveyQuestion", back_populates="answers")

    @property
    def choice_ids_list(self) -> list[str]:
        if not self.value_choice_ids:
            return []
        try:
            return json.loads(self.value_choice_ids)
        except (json.JSONDecodeError, TypeError):
            return []
