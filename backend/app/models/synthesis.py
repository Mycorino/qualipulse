"""CrossStudySynthesis — a decision memo synthesised across several Studies.

Where ProjectAnalysis is one study's qualitative synthesis and StudyAnalysis
is one study's mixed-methods (survey + interview) report, this row sits one
level above both: the researcher picks 2..N completed studies and gets a
single decision-oriented memo (verdict, converging/conflicting evidence,
gaps, recommendations) generated from those studies' *final analyses* — the
transcripts themselves are never re-read at this level.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CrossStudySynthesis(Base):
    __tablename__ = "cross_study_syntheses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # The decision the researcher wants this memo to inform (free text).
    decision_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list of Study ids included in the synthesis.
    study_ids: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="generating", nullable=False
    )  # generating | ready | failed
    # Decision-memo JSON blob — shape defined in services/study_synthesis.py.
    report: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    company = relationship("Company")
