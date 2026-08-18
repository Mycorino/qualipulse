import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InterviewLink(Base):
    __tablename__ = "interview_links"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Optional ceiling on how many participants this link may admit. Protects a
    # shared link that leaks (forwarded, posted publicly) from draining the
    # workspace's interview credits: once the cap is reached the link stops
    # admitting new participants but in-progress interviews still finish.
    # None = uncapped (the historical behaviour).
    max_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    project = relationship("Project", back_populates="interview_links")
    participants = relationship(
        "Participant", back_populates="link", cascade="all, delete-orphan"
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    link_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview_links.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age_range: Mapped[str | None] = mapped_column(String(20), nullable=True)
    profession: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Denormalised from PanelProfile.panel_consent (matched by email) when the
    # interview completes or the panel profile is saved — gives researchers a
    # per-participant "OK to recontact" flag without joining panel_profiles.
    # None = unknown (pre-feature rows), False = declined, True = consented.
    panel_consent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Participant-chosen interview language — overrides Project.language for the
    # AI interviewer + voice when set (en/fr/de/es/it/pt).
    preferred_language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="in_progress", nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quality_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_strengths: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    quality_issues: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    # Interview digest — filled by the same auto-run Claude pass as the quality
    # assessment so a researcher opening a fresh transcript gets an instant
    # read without triggering the project-level analysis.
    key_takeaways: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    notable_quotes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list (verbatim)
    avg_response_words: Mapped[float | None] = mapped_column(Float, nullable=True)
    short_answer_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    link = relationship("InterviewLink", back_populates="participants")
    project = relationship("Project", back_populates="participants")
    turns = relationship(
        "InterviewTurn", back_populates="participant", cascade="all, delete-orphan"
    )


class ProjectAnalysis(Base):
    __tablename__ = "project_analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="generating", nullable=False
    )  # "generating" | "ready" | "failed"
    # Pipeline stage while status == "generating":
    # "auto_tagging" | "preparing" | "synthesizing" | "verifying". NULL once
    # the run leaves the generating state (ready/failed) and on pre-stage rows.
    stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # JSON blob of stage progress counters, e.g. {"done": 3, "total": 10}
    # during auto_tagging. NULL when the stage has no counters.
    stage_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    filters: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: {filter_by, filter_values}
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    researcher_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    version_label: Mapped[str] = mapped_column(String(20), default="ai_discovery", nullable=False)
    parent_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("project_analyses.id", ondelete="SET NULL"), nullable=True
    )
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    project = relationship("Project", back_populates="analyses")
    annotations = relationship(
        "AnalysisThemeAnnotation", back_populates="analysis", cascade="all, delete-orphan"
    )


class AnalysisThemeAnnotation(Base):
    __tablename__ = "analysis_theme_annotations"
    __table_args__ = (UniqueConstraint("analysis_id", "theme_title", name="uq_annotation_analysis_theme"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    analysis_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("project_analyses.id", ondelete="CASCADE"), nullable=False
    )
    theme_title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # confirmed | disputed | needs_evidence
    researcher_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )

    analysis = relationship("ProjectAnalysis", back_populates="annotations")


class InterviewTurn(Base):
    __tablename__ = "interview_turns"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    participant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_follow_up: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    follow_up_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whisper segment timestamps as JSON: [{"start": float, "end": float, "text": str}]
    # Powers sentence-level highlighting in the researcher transcript view.
    # Cleared on manual edit because character offsets no longer match.
    response_segments: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tts_audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Translation cache: response and question translated to researcher's language
    translated_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation_language: Mapped[str | None] = mapped_column(String(5), nullable=True)
    translation_source_language: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # ASR sense-check cache: a Haiku pass that fixes obvious STT errors (proper
    # nouns, domain homophones) using study context. The original
    # response_transcript is the data and is never overwritten; this is a
    # display + translation-source reading aid, same principle as translation.
    cleaned_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    cleaned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    participant = relationship("Participant", back_populates="turns")
    quote_tags = relationship("QuoteTag", back_populates="turn", cascade="all, delete-orphan")
