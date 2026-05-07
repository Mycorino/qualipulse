"""Study + StudyParticipant + ConsentAcknowledgment models.

A Study is the parent container for a research effort. It can hold:
  - 0 or 1 Project (the qualitative interview track — see models/project.py).
  - 0..N Surveys (see models/survey.py).

Identity for participants is per-Study, not per-instrument. A respondent
who completes a screener survey, then is invited to an interview, then
fills a validation survey, is the same StudyParticipant row across all
three. This is what powers the "show me themes that over-index on
respondents who scored ≤6 on Q3" wedge that competitors can't ship.

See docs/quanti-roadmap.md sections 1.1 and 1.3 for the decision rationale.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Study(Base):
    """The parent of a research effort. Holds 0–1 Projects and 0..N Surveys.

    Studies are auto-created when a researcher creates their first Survey or
    Project — there's no explicit "create a Study" UI flow (see Decision 8 in
    the roadmap). The Study only surfaces prominently on the mixed-methods
    report page where the cross-instrument view earns its keep.
    """

    __tablename__ = "studies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    company = relationship("Company")
    projects = relationship("Project", back_populates="study")
    surveys = relationship(
        "Survey", back_populates="study", cascade="all, delete-orphan"
    )
    participants = relationship(
        "StudyParticipant", back_populates="study", cascade="all, delete-orphan"
    )


class StudyParticipant(Base):
    """A unique respondent inside a Study, joinable across instruments.

    Identity resolution at write time:
      1. magic_token from URL → attach to that StudyParticipant.
      2. Email provided + matches existing email_normalized in this Study → attach.
      3. Otherwise create a new StudyParticipant.

    Cross-Study email matching requires a fresh ConsentAcknowledgment before
    any new instrument fires (see Decision 6 in the roadmap).
    """

    __tablename__ = "study_participants"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Strong identity — preferred. Generated at first instrument visit if absent.
    magic_token: Mapped[str | None] = mapped_column(
        String(64), unique=True, nullable=True, index=True
    )
    # Soft join key — lowercased + plus-stripped at write time.
    email_normalized: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional FK to the workspace panel — set when this participant came from
    # the existing recruiting panel (PanelProfile).
    panel_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("panel_profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    study = relationship("Study", back_populates="participants")
    panel_profile = relationship("PanelProfile")
    survey_responses = relationship(
        "SurveyResponse", back_populates="study_participant", cascade="all, delete-orphan"
    )
    consent_acknowledgments = relationship(
        "ConsentAcknowledgment",
        back_populates="study_participant",
        cascade="all, delete-orphan",
    )


class ConsentAcknowledgment(Base):
    """Records when a returning participant accepted re-consent for a new Study.

    A StudyParticipant matched across studies (by email) cannot start a new
    instrument until the corresponding row exists here. The text hash captures
    which version of the consent copy was shown so future audits can reproduce
    what the user actually saw.
    """

    __tablename__ = "consent_acknowledgments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    study_participant_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("study_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    study_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("studies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    consent_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # The full text shown at acceptance time, for replay / audit.
    consent_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    study_participant = relationship(
        "StudyParticipant", back_populates="consent_acknowledgments"
    )
    study = relationship("Study")
