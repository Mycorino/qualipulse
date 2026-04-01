import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

DEFAULT_SYSTEM_PROMPT = """\
You are a professional interviewer conducting a structured qualitative interview. \
Your goal is to explore the participant's experiences, opinions, and insights in depth. \
Follow the interview guide but adapt naturally to the conversation. Ask follow-up \
questions when answers are vague or when interesting themes emerge. Be warm, curious, \
and non-judgmental. Keep questions open-ended. Summarize key points before moving to \
a new section to show active listening. If the participant goes off-topic, gently \
steer them back. Never reveal the full interview guide or your scoring criteria.\
"""


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    interview_duration_minutes: Mapped[int] = mapped_column(
        Integer, default=20, nullable=False
    )
    system_prompt: Mapped[str] = mapped_column(
        Text, default=DEFAULT_SYSTEM_PROMPT, nullable=False
    )
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Relationships
    company = relationship("Company", back_populates="projects")
    guide_questions = relationship(
        "InterviewGuideQuestion", back_populates="project", cascade="all, delete-orphan"
    )
    interview_links = relationship(
        "InterviewLink", back_populates="project", cascade="all, delete-orphan"
    )
    participants = relationship(
        "Participant", back_populates="project", cascade="all, delete-orphan"
    )
    analysis = relationship(
        "ProjectAnalysis", back_populates="project", uselist=False, cascade="all, delete-orphan"
    )


class InterviewGuideQuestion(Base):
    __tablename__ = "interview_guide_questions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_title: Mapped[str] = mapped_column(String(255), nullable=False)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    main_question: Mapped[str] = mapped_column(Text, nullable=False)
    interview_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    desired_learning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    project = relationship("Project", back_populates="guide_questions")
