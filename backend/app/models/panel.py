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
    # Stats
    interviews_completed = Column(Integer, default=0)
    last_active = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # Relations
    tags = relationship("PanelTag", secondary=panel_profile_tags, back_populates="profiles")


class PanelTag(Base):
    __tablename__ = "panel_tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    category = Column(String, nullable=False)  # "interest","behavior","consumer"
    profiles = relationship("PanelProfile", secondary=panel_profile_tags, back_populates="tags")


class ParticipantMagicToken(Base):
    __tablename__ = "participant_magic_tokens"

    id = Column(Integer, primary_key=True)
    email = Column(String, nullable=False, index=True)
    token = Column(String, unique=True, nullable=False, index=True)
    interview_link_token = Column(String, nullable=False)
    used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
