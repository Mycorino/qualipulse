"""Research Copilot — persistent state.

``CopilotMemory`` — scoped, durable memory. A row is keyed by
``(scope_kind, scope_id)``:
  - company: workspace-wide facts (scope_id = company id)
  - study:   facts about one research effort (scope_id = study id)
  - survey:  facts about one survey (scope_id = survey id)
The copilot stacks every applicable tier into its system prompt.

``CopilotConversation`` — one persisted chat thread per survey, so the
panel resumes the conversation instead of losing it on navigation.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Memory scope tiers. "company" and "study" are shared; the instrument
# tier is "survey" or "project" depending on which surface the copilot
# is running on.
MEMORY_SCOPES = ("company", "study", "survey", "project")


class CopilotMemory(Base):
    __tablename__ = "copilot_memory"
    __table_args__ = (
        Index("ix_copilot_memory_scope", "scope_kind", "scope_id", unique=True),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # Owning workspace — drives cascade delete and access checks.
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "company" | "study" | "survey"
    scope_kind: Mapped[str] = mapped_column(
        String(16), default="company", nullable=False
    )
    # company id / study id / survey id, per scope_kind.
    scope_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Free-text markdown of durable facts the copilot has learned.
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    company = relationship("Company")


class CopilotConversation(Base):
    """One persisted chat thread per instrument (survey or project).

    Keyed by ``(scope_kind, scope_id)`` — ``scope_kind`` is "survey" or
    "project", ``scope_id`` the instrument id. The panel reloads this on
    mount so the conversation resumes instead of being lost on navigation.
    """

    __tablename__ = "copilot_conversations"
    __table_args__ = (
        Index(
            "ix_copilot_conversations_scope",
            "scope_kind",
            "scope_id",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    company_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "survey" | "project"
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # survey id / project id, per scope_kind.
    scope_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # JSON array of the panel's thread items (user/assistant turns +
    # proposal cards with their accepted/rejected status).
    thread: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    company = relationship("Company")
