import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
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
    status: Mapped[str] = mapped_column(
        String(20), default="in_progress", nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="generating", nullable=False
    )  # "generating" | "ready" | "failed"
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON blob
    filters: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON: {filter_by, filter_values}
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    project = relationship("Project", back_populates="analysis")


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
    audio_recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tts_audio_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    manually_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    participant = relationship("Participant", back_populates="turns")
    quote_tags = relationship("QuoteTag", back_populates="turn", cascade="all, delete-orphan")
