"""Research plan — multi-step orchestration over time.

A `ResearchPlan` is the long-running research program a researcher commits
to at the end of onboarding. Each `ResearchPlanStep` is one method in
that plan (e.g. quant survey → qual interviews → quant validation).

Individual `Project` rows reference their parent plan + step so the UI
can show "Study 1 of 3 in your ticket-purchase plan." This is the v1
schema — actually drafting plan-step methods other than voice interviews
is a follow-up; for now step 1 of every plan creates a real Project as
today, and steps 2+ are placeholders that the researcher activates later.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ResearchPlan(Base):
    __tablename__ = "research_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String, ForeignKey("companies.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Free-text strategic context captured during onboarding — same
    # fields a single-study proposal would have, lifted up to the plan
    # level because they describe the whole research effort.
    decision_to_inform: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline: Mapped[str | None] = mapped_column(String, nullable=True)
    success_criteria: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_customer_description: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    steps: Mapped[list["ResearchPlanStep"]] = relationship(
        "ResearchPlanStep",
        back_populates="plan",
        order_by="ResearchPlanStep.order_index",
        cascade="all, delete-orphan",
    )


class ResearchPlanStep(Base):
    __tablename__ = "research_plan_steps"
    __table_args__ = (
        UniqueConstraint("plan_id", "order_index", name="uq_plan_step_order"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    plan_id: Mapped[str] = mapped_column(
        String, ForeignKey("research_plans.id"), nullable=False, index=True
    )

    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False)
    # 'voice_interview' | 'quant_survey' | 'workshop' | 'desk_research' |
    # 'usability_test' — extensible. v1 only really drafts
    # `voice_interview` automatically; the others are placeholders that
    # the user will activate manually later.

    title: Mapped[str] = mapped_column(String, nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    deliverable: Mapped[str | None] = mapped_column(Text, nullable=True)
    n_participants: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # If/when this step has been drafted as an actual Project, the FK
    # back to it. Null = not yet started.
    project_id: Mapped[str | None] = mapped_column(
        String, ForeignKey("projects.id"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending"
    )
    # 'pending' | 'drafted' | 'in_progress' | 'completed'

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    plan: Mapped[ResearchPlan] = relationship(
        "ResearchPlan", back_populates="steps"
    )
