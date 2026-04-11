import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Onboarding profile
    company_size: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # "1-10" | "11-50" | "51-200" | "201-1000" | "1000+"
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # "Researcher" | "Product Manager" | "Designer" | "Founder" | "Marketing" | "Other"
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    use_case: Mapped[str | None] = mapped_column(String(100), nullable=True)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Enhanced onboarding
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    business_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    research_experience: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # "new" | "some" | "professional"
    primary_region: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # "europe" | "north_america" | "apac" | "global" | "other"
    goals_freeform: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Business context (used to ground AI analysis + research suggestions)
    value_proposition: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_competitors: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # "idea" | "mvp" | "growth" | "scale"
    customer_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # "b2c" | "b2b" | "b2b2c" | "internal"

    # Qualification signals for sales routing
    interviews_per_month_target: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # "0-5" | "5-20" | "20-50" | "50+"
    current_tool: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Free-form with suggestions: "Nothing yet" | "User interviews (service)" | "Dovetail" | etc.
    decision_role: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # "buyer" | "influencer" | "user" | "evaluator"
    goals_classification: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Claude-classified bucket(s), e.g. "product_discovery,customer_retention"

    # Subscription
    subscription_tier: Mapped[str] = mapped_column(String(20), default="starter", nullable=False)
    # "starter" | "team" | "lab" | "enterprise"
    subscription_status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # "active" | "past_due" | "canceled" | "trialing"
    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    interview_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(5), default="fr", nullable=False)

    # Integrations
    slack_webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamp of when the onboarding showcase/demo project was seeded for
    # this company. Used to keep the seeder idempotent — if it's non-null
    # we skip seeding on subsequent onboarding-complete calls (e.g. when a
    # user re-opens the welcome flow after clearing localStorage).
    demo_seeded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    projects = relationship("Project", back_populates="company", cascade="all, delete-orphan")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True,
        default=lambda: secrets.token_urlsafe(32),
        nullable=False
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )

    company = relationship("Company", backref="reset_tokens")


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, index=True,
        default=lambda: secrets.token_urlsafe(32),
        nullable=False
    )
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.utcnow(), nullable=False
    )

    company = relationship("Company", backref="verification_tokens")
