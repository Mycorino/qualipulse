import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ManualCode(Base):
    """A researcher-defined code for tagging quotes."""
    __tablename__ = "manual_codes"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#6366f1")  # hex color
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    project = relationship("Project", back_populates="manual_codes")
    quote_tags = relationship("QuoteTag", back_populates="code", cascade="all, delete-orphan")


class QuoteTag(Base):
    """A tagged segment of text in an interview turn."""
    __tablename__ = "quote_tags"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    turn_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("interview_turns.id", ondelete="CASCADE"), nullable=False
    )
    manual_code_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("manual_codes.id", ondelete="CASCADE"), nullable=False
    )
    selected_text: Mapped[str] = mapped_column(Text, nullable=False)
    start_index: Mapped[int] = mapped_column(Integer, nullable=False)
    end_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    turn = relationship("InterviewTurn", back_populates="quote_tags")
    code = relationship("ManualCode", back_populates="quote_tags")
