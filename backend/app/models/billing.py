"""SQLAlchemy models for the credits-based billing system.

Tables added in migration ``0022_credits_system``. Legacy
``Company.subscription_tier`` remains in place for backward compatibility —
the new ``WorkspaceSubscription`` is the source of truth going forward, but
old surfaces that read ``Company.subscription_tier`` directly continue to
work until they're migrated.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_str() -> str:
    return str(uuid.uuid4())


class Plan(Base):
    """Catalogue of billing plans — legacy and new, public and custom."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    public_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_legacy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    monthly_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")

    included_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 'trial_total' | 'monthly' | 'annual' | 'custom' | 'legacy_none'
    credit_period: Mapped[str] = mapped_column(String(20), nullable=False)

    max_editors: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_viewers: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_active_projects: Mapped[int | None] = mapped_column(Integer, nullable=True)

    overage_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overage_enabled_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    stripe_monthly_price_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_annual_price_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    entitlements = relationship(
        "PlanEntitlement", back_populates="plan", cascade="all, delete-orphan"
    )


class PlanEntitlement(Base):
    """Capability flag attached to a plan.

    Examples::

        ("csv_export", true)
        ("custom_branding", true)
        ("credit_rollover_days", 30)
        ("credit_rollover_cap_ratio", 0.25)
    """

    __tablename__ = "plan_entitlements"
    __table_args__ = (UniqueConstraint("plan_id", "key", name="uq_plan_entitlement_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    plan = relationship("Plan", back_populates="entitlements")


class WorkspaceSubscription(Base):
    """A workspace's current (or past) plan + Stripe linkage.

    ``workspace_id`` == ``Company.id`` in this codebase. The naming leaves
    headroom for splitting workspaces from the billing entity later.
    """

    __tablename__ = "workspace_subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(String(50), ForeignKey("plans.id"), nullable=False)
    # 'trialing' | 'active' | 'past_due' | 'canceled' | 'unpaid' | 'enterprise_custom' | 'legacy'
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    # 'monthly' | 'annual' | 'custom' | 'legacy'
    billing_interval: Mapped[str | None] = mapped_column(String(20), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    trial_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    stripe_customer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    overage_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    plan = relationship("Plan")


class CreditBalance(Base):
    """Per-period credit pool for a workspace.

    Available at any moment::

        included + purchased + rollover - used
    """

    __tablename__ = "credit_balances"
    __table_args__ = (
        UniqueConstraint("workspace_id", "period_start", "period_end", name="uq_credit_balance_period"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("workspace_subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    period_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    included_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    purchased_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rollover_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overage_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)

    @property
    def available(self) -> int:
        return (
            (self.included_credits or 0)
            + (self.purchased_credits or 0)
            + (self.rollover_credits or 0)
            - (self.used_credits or 0)
        )


class CreditLedger(Base):
    """Append-only audit trail of every credit movement.

    Idempotency rule: at most one ``consume_interview`` or
    ``overage_interview`` row per ``participant_id``. Enforced by a partial
    unique index (declared below); the BillingService also checks before
    inserting so concurrent calls fail fast rather than crash on the
    constraint.
    """

    __tablename__ = "credit_ledger"
    __table_args__ = (
        # Partial unique index — supported by Postgres and SQLite (3.8+).
        # Declared on the model too so ``Base.metadata.create_all`` picks it
        # up on fresh dev databases (alembic also has it in 0022).
        Index(
            "uq_credit_consumed_per_participant",
            "participant_id",
            unique=True,
            postgresql_where=sa_text("event_type IN ('consume_interview', 'overage_interview')"),
            sqlite_where=sa_text("event_type IN ('consume_interview', 'overage_interview')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    balance_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("credit_balances.id", ondelete="SET NULL"), nullable=True
    )
    participant_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    credits_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str | None] = mapped_column(String(40), nullable=True)
    event_metadata: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow)


class UsageEvent(Base):
    """Analytics-grade timeline of billable / billable-adjacent events.

    Distinct from ``credit_ledger``: ledger is the canonical source of truth
    for credit balances; usage events are an event-sourced stream for
    dashboards, alerts, and finance reports.
    """

    __tablename__ = "usage_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)
    workspace_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    participant_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    event_name: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    event_metadata: Mapped[Any | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow, index=True)
