"""Credits-based billing system — V1 foundation.

Introduces the credits-based pricing model alongside the existing tier-based
gates. The new system runs in parallel: plans flagged ``is_legacy`` route
quota decisions through ``feature_gates.require_participant_limit`` (current
behaviour), while non-legacy plans (trial / exploration / team / agency /
enterprise) consume credits per completed participant.

Tables created:
- ``plans``                  — catalogue of all plans (legacy + new + custom)
- ``plan_entitlements``      — flexible key/value capability flags per plan
- ``workspace_subscriptions``— each company's current plan + Stripe linkage
- ``credit_balances``        — per-period credit pool (granted / used / overage)
- ``credit_ledger``          — append-only audit trail of every credit movement
- ``usage_events``           — analytics-grade timeline of billable events

Idempotency invariant: a participant can consume credit at most once.
Enforced via a partial unique index on ``credit_ledger(participant_id)``
filtered to ``event_type IN ('consume_interview', 'overage_interview')``.

The migration is purely additive — existing ``companies`` columns
(``subscription_tier``, ``stripe_customer_id``, etc.) stay in place. A
follow-up migration may consolidate them once we're confident the new
service is the source of truth.

Revision ID: 0022_credits_system
Revises: 0021_response_segments
Create Date: 2026-05-03
"""
from alembic import op
import sqlalchemy as sa


revision = "0022_credits_system"
down_revision = "0021_response_segments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── plans ────────────────────────────────────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", sa.String(50), primary_key=True),
        sa.Column("public_name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_legacy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("monthly_price_cents", sa.Integer(), nullable=True),
        sa.Column("annual_price_cents", sa.Integer(), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="EUR"),
        sa.Column("included_credits", sa.Integer(), nullable=True),
        # 'trial_total' | 'monthly' | 'annual' | 'custom' | 'legacy_none'
        sa.Column("credit_period", sa.String(20), nullable=False),
        sa.Column("max_editors", sa.Integer(), nullable=True),
        sa.Column("max_viewers", sa.Integer(), nullable=True),
        sa.Column("max_active_projects", sa.Integer(), nullable=True),
        sa.Column("overage_price_cents", sa.Integer(), nullable=True),
        sa.Column("overage_enabled_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stripe_monthly_price_id", sa.String(100), nullable=True),
        sa.Column("stripe_annual_price_id", sa.String(100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )

    # ── plan_entitlements ────────────────────────────────────────────────────
    # Capability flags expressed as JSON values so we don't need a column per
    # feature. Examples: ('csv_export', true), ('credit_rollover_days', 30).
    op.create_table(
        "plan_entitlements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("plan_id", sa.String(50), sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("plan_id", "key", name="uq_plan_entitlement_key"),
    )
    op.create_index("ix_plan_entitlements_plan_id", "plan_entitlements", ["plan_id"])

    # ── workspace_subscriptions ──────────────────────────────────────────────
    # workspace_id == company_id in this codebase. Named for forward
    # compatibility if we ever split workspaces from companies.
    op.create_table(
        "workspace_subscriptions",
        sa.Column("id", sa.String(36), primary_key=True),  # uuid as text for SQLite
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_id", sa.String(50), sa.ForeignKey("plans.id"), nullable=False),
        # 'trialing' | 'active' | 'past_due' | 'canceled' | 'unpaid' | 'enterprise_custom' | 'legacy'
        sa.Column("status", sa.String(30), nullable=False),
        # 'monthly' | 'annual' | 'custom' | 'legacy'
        sa.Column("billing_interval", sa.String(20), nullable=True),
        sa.Column("current_period_start", sa.DateTime(), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("trial_start", sa.DateTime(), nullable=True),
        sa.Column("trial_end", sa.DateTime(), nullable=True),
        sa.Column("stripe_customer_id", sa.String(100), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(100), nullable=True),
        sa.Column("stripe_price_id", sa.String(100), nullable=True),
        sa.Column("overage_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    # One active subscription per workspace. Cancelled rows are kept for
    # history; the service queries the most recent.
    op.create_index("ix_workspace_subscriptions_workspace", "workspace_subscriptions", ["workspace_id"])
    op.create_index("ix_workspace_subscriptions_stripe_sub", "workspace_subscriptions", ["stripe_subscription_id"])

    # ── credit_balances ──────────────────────────────────────────────────────
    op.create_table(
        "credit_balances",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.String(36), sa.ForeignKey("workspace_subscriptions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("period_start", sa.DateTime(), nullable=False),
        sa.Column("period_end", sa.DateTime(), nullable=False),
        sa.Column("included_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("purchased_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rollover_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("used_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overage_credits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("workspace_id", "period_start", "period_end", name="uq_credit_balance_period"),
    )
    op.create_index("ix_credit_balances_workspace", "credit_balances", ["workspace_id"])

    # ── credit_ledger ────────────────────────────────────────────────────────
    # Append-only. Every credit movement (grant, consume, refund, adjust,
    # expire) writes one row. Reconstruct the balance for any point-in-time
    # by summing ``credits_delta`` up to that moment.
    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("balance_id", sa.String(36), sa.ForeignKey("credit_balances.id", ondelete="SET NULL"), nullable=True),
        sa.Column("participant_id", sa.String(36), nullable=True),  # not FK — participants can be deleted
        sa.Column("project_id", sa.String(36), nullable=True),
        # 'grant_included' | 'grant_purchased' | 'grant_rollover' |
        # 'consume_interview' | 'overage_interview' |
        # 'refund_interview' | 'adjustment_admin' | 'expire_credits'
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("credits_delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=True),
        # 'subscription_renewal' | 'stripe_checkout' | 'interview_completed' |
        # 'admin_manual' | 'migration' | 'webhook'
        sa.Column("source", sa.String(40), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_credit_ledger_workspace", "credit_ledger", ["workspace_id"])
    op.create_index("ix_credit_ledger_participant", "credit_ledger", ["participant_id"])
    op.create_index("ix_credit_ledger_event_type", "credit_ledger", ["event_type"])

    # Idempotency lock: one consume/overage row per participant, ever.
    # Partial index — supported by both Postgres and SQLite (3.8+).
    # In SQLite the syntax is `CREATE UNIQUE INDEX ... WHERE ...`; SQLAlchemy
    # accepts the `postgresql_where` arg but for cross-dialect we declare it
    # with the generic `sqlite_where` + `postgresql_where` pair.
    op.create_index(
        "uq_credit_consumed_per_participant",
        "credit_ledger",
        ["participant_id"],
        unique=True,
        postgresql_where=sa.text("event_type IN ('consume_interview', 'overage_interview')"),
        sqlite_where=sa.text("event_type IN ('consume_interview', 'overage_interview')"),
    )

    # ── usage_events ─────────────────────────────────────────────────────────
    op.create_table(
        "usage_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("participant_id", sa.String(36), nullable=True),
        sa.Column("event_name", sa.String(60), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_usage_events_workspace", "usage_events", ["workspace_id"])
    op.create_index("ix_usage_events_event_name", "usage_events", ["event_name"])
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("usage_events")
    op.drop_index("uq_credit_consumed_per_participant", table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_table("credit_balances")
    op.drop_table("workspace_subscriptions")
    op.drop_table("plan_entitlements")
    op.drop_table("plans")
