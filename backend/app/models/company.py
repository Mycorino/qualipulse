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
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Google OAuth — Google's stable user identifier ("sub" claim). Null for
    # password-only accounts. Unique so two Google accounts can't share one.
    google_sub: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True
    )
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
    # How the researcher found us. Marketing attribution + cohort
    # analysis depend on this. Free-text with suggested chips
    # (Google / LinkedIn / Colleague / Other). Alembic 0033.
    referral_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Measured first-touch attribution, captured from the landing URL by the
    # SPA and carried through signup. Distinct from ``referral_source``,
    # which is what the user *says* when asked. Alembic 0064.
    utm_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_medium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    utm_campaign: Mapped[str | None] = mapped_column(String(100), nullable=True)
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

    # Workspace-level participant-branding defaults, prefilled into every
    # new study (each study's own Setup tab keeps the final say). JSON dict
    # of the Project branding fields: branding_mode / brand_primary_color /
    # brand_font / researcher_name / researcher_logo_url / privacy_policy_url.
    branding_defaults: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def branding_defaults_dict(self) -> dict:
        import json

        try:
            return json.loads(self.branding_defaults) if self.branding_defaults else {}
        except (ValueError, TypeError):
            return {}

    # Onboarding redesign — personal identity + recap
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    occupation_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_use_cases: Mapped[str | None] = mapped_column(Text, nullable=True)
    onboarding_recap: Mapped[str | None] = mapped_column(Text, nullable=True)
    study_readiness: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Current priority — monthly re-prompt on the Dashboard so the researcher's
    # top-of-mind focus stays fresh. The UI nudges them to update this every
    # ~30 days. Free-form text so they can write "understanding why X churned"
    # or whatever matches their context.
    current_priority: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_priority_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Timestamp of when the onboarding showcase/demo project was seeded for
    # this company. Used to keep the seeder idempotent — if it's non-null
    # we skip seeding on subsequent onboarding-complete calls (e.g. when a
    # user re-opens the welcome flow after clearing localStorage).
    demo_seeded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Set the first time a participant completes an interview anywhere in
    # this workspace. Idempotency guard for the "your first response is
    # in" lifecycle email — fire-once, never re-send (the trigger is
    # special; "every response" would be spam). Alembic 0023.
    first_response_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Cache for the personalised /welcome greeting generated by Haiku
    # from the wizard-captured profile + business summary. 24h TTL —
    # the endpoint regenerates if `welcome_greeting_at` is older than
    # 24h or null. Alembic 0036.
    welcome_greeting_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_greeting_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Cache for the personalised starter-question chips on /welcome
    # Phase 2. JSON-serialised list of 3 short strings. Same 24h TTL.
    # Alembic 0036.
    starter_suggestions_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    starter_suggestions_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Cache for the personalised mid-conversation opening question the
    # participant-demo modal asks. Generated by Haiku from captured
    # role + company + business_summary + use_case so the demo opens
    # like turn 2 of a real conversation rather than a cold prompt.
    # 24h TTL. Alembic 0038.
    demo_opening_question_text: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    demo_opening_question_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Sticky flag set the first time a real paid subscription becomes
    # active. Once true, never resets — even on cancellation, ex-paying
    # customers retain read-only access to data they collected. Drives
    # the free-tier "first 3 transcripts visible" paywall: paid OR
    # ever-paid = no paywall; pure free = first 3 visible only. Alembic
    # 0034. Backfilled at migration time for legacy paid accounts.
    has_ever_paid: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )

    # V4 paywall milestone — set when the 3rd participant completes
    # and we send the "free preview full, unlock the rest" email.
    # Idempotency guard so we don't re-pitch on every subsequent
    # completion. Alembic 0034.
    free_preview_full_email_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    # Admin — account suspension
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Security (Alembic 0051) ───────────────────────────────────────
    # Monotonic session-revocation counter. Every JWT carries the value it
    # was minted with ("tv" claim); a mismatch on decode = token revoked.
    # Bumped on password change/reset, "log out everywhere", and admin
    # suspension. Tokens minted before the column existed carry no claim
    # and are treated as tv=0.
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    # TOTP two-factor auth. ``totp_secret`` is set at setup time but 2FA
    # only enforces once ``totp_enabled`` flips true (after the user has
    # proven their authenticator with a valid code). Backup codes are
    # stored as a JSON list of SHA-256 hex digests — high-entropy codes,
    # so a fast hash is fine (unlike passwords).
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default="0"
    )
    totp_backup_codes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Brute-force lockout: consecutive failed password / 2FA attempts.
    # 5 failures → locked_until = now + 15 min; reset on success.
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, server_default="0"
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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
