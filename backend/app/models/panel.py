import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base

# Many-to-many: PanelProfile <-> PanelTag
panel_profile_tags = Table(
    "panel_profile_tags",
    Base.metadata,
    Column("profile_id", Integer, ForeignKey("panel_profiles.id", ondelete="CASCADE")),
    Column("tag_id", Integer, ForeignKey("panel_tags.id", ondelete="CASCADE")),
)


class PanelProfile(Base):
    __tablename__ = "panel_profiles"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    first_name = Column(String, nullable=True)
    # Demographics
    age_range = Column(String, nullable=True)   # "18-24","25-34","35-44","45-54","55+"
    gender = Column(String, nullable=True)       # "male","female","non_binary","prefer_not"
    country = Column(String, nullable=True)
    city = Column(String, nullable=True)
    education = Column(String, nullable=True)    # "high_school","bachelor","master","phd","other"
    employment_status = Column(String, nullable=True)  # "full_time","part_time","freelance","student","unemployed","retired"
    job_function = Column(String, nullable=True)  # "engineering","product","marketing","design","finance","operations","hr","executive","other"
    seniority = Column(String, nullable=True)    # "junior","mid","senior","manager","director","c_suite"
    industry = Column(String, nullable=True)
    company_size = Column(String, nullable=True)  # "1","2-10","11-50","51-200","201-1000","1000+"
    # Preferred language for participant-facing comms (interview + future study invites)
    preferred_language = Column(String, nullable=True)  # "en","fr","de","es","it","pt"
    # Panel
    panel_consent = Column(Boolean, default=False)
    consent_at = Column(DateTime, nullable=True)
    consent_interview_token = Column(String, nullable=True)
    # Explicit special-category (GDPR Art. 9) consent for sensitive enrichment
    # attributes (health / income / politics / religion). Separate from the
    # base panel_consent so we have a distinct lawful basis on record.
    sensitive_data_consent = Column(Boolean, default=False)
    sensitive_data_consent_at = Column(DateTime, nullable=True)
    # Stats
    interviews_completed = Column(Integer, default=0)
    last_active = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Relations
    tags = relationship("PanelTag", secondary=panel_profile_tags, back_populates="profiles")
    answers = relationship(
        "PanelAnswer", back_populates="profile", cascade="all, delete-orphan"
    )


class PanelTag(Base):
    __tablename__ = "panel_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    category = Column(String, nullable=False)  # "interest","behavior","consumer"
    profiles = relationship("PanelProfile", secondary=panel_profile_tags, back_populates="tags")


class PanelAttribute(Base):
    """The profiling question bank — a seeded catalogue of enrichment questions
    (smoking, pets, income band, shopping habits, brand affinities, …). One row
    per question; panelists answer a subset via PanelAnswer. Adding the 51st
    attribute is a catalogue row, not a schema migration.

    Labels live on the row as a per-locale JSON blob so the catalogue stays
    data-driven (no frontend i18n edit + redeploy to add an attribute).
    """
    __tablename__ = "panel_attributes"

    id = Column(String, primary_key=True)  # stable key, e.g. "smoking_status"
    category = Column(String, nullable=False, index=True)  # household, lifestyle, finance, ...
    type = Column(String, nullable=False)  # "single" | "multi" | "bool" | "scale"
    options = Column(Text, nullable=True)  # JSON: [{"value": str, "label_i18n": {locale: str}}]
    label_i18n = Column(Text, nullable=False)  # JSON: {locale: question text}
    is_sensitive = Column(Boolean, default=False, nullable=False)
    priority = Column(Integer, default=0, nullable=False)  # higher = more re-targeting value
    sort_order = Column(Integer, default=0, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    answers = relationship("PanelAnswer", back_populates="attribute")


class PanelAnswer(Base):
    """One panelist's answer to one PanelAttribute. Upserted (unique per
    profile+attribute). ``value`` is JSON — a string (single/scale), a list
    (multi), or a bool — interpreted per the attribute's ``type``.
    """
    __tablename__ = "panel_answers"
    __table_args__ = (
        UniqueConstraint("profile_id", "attribute_id", name="uq_panel_answer"),
    )

    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(
        Integer, ForeignKey("panel_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attribute_id = Column(
        String, ForeignKey("panel_attributes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value = Column(Text, nullable=False)  # JSON-encoded
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("PanelProfile", back_populates="answers")
    attribute = relationship("PanelAttribute", back_populates="answers")


class StudyInvite(Base):
    """One recontact invitation: a consented panelist asked to take part in a
    specific study. Append-only — funnel status (started / completed) is never
    stored here but derived by joining ``participants`` on
    ``(project_id, lower(email))``, so replayed webhooks or engine changes
    can't desync it. The unique constraint makes re-sends to the same person
    for the same study impossible at the schema level.
    """
    __tablename__ = "study_invites"
    __table_args__ = (
        UniqueConstraint("project_id", "email", name="uq_invite_per_project_email"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id = Column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Workspace owner of the project at send time — denormalised so the pool
    # page and daily-cap queries never need a join through projects.
    company_id = Column(String(36), nullable=False, index=True)
    profile_id = Column(
        Integer, ForeignKey("panel_profiles.id", ondelete="SET NULL"), nullable=True
    )
    email = Column(String, nullable=False, index=True)  # lowercased at write
    language = Column(String, nullable=True)  # locale the email was sent in
    sent_by = Column(String(36), nullable=True)  # company id of the sending user
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


class ParticipantMagicToken(Base):
    __tablename__ = "participant_magic_tokens"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    interview_link_token = Column(String, nullable=False)
    used = Column(Boolean, default=False)
    # Recontact invites mint a token that is NOT burned on first click.
    # The session JWT it issues lasts only 2 hours, so a single-use invite
    # would lock a panelist out of their own invitation the moment they
    # stepped away and came back, with no way to re-request one. Reuse is
    # safe here because the token is bound to a single email and the
    # one-completed-interview-per-email-per-link guard still applies, so a
    # forwarded or re-clicked invite can never yield a second interview.
    reusable = Column(Boolean, default=False, nullable=False, server_default="0")
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
