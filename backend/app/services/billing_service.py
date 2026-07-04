"""Central billing service for the credits-based pricing system.

Ground rules
------------
* ``workspace_id == company_id``. The ``WorkspaceSubscription`` model uses
  ``workspace_id`` as its FK column for forward compat; the values are
  always Company UUIDs.
* The ``plans`` row's ``is_legacy`` flag drives the quota strategy:
  legacy plans defer to the existing ``feature_gates`` participant-limit
  check; non-legacy plans run the credit-based flow defined here.
* Credit consumption is **idempotent** per participant. Enforced both
  application-side (we check the ledger before inserting) and at the DB
  via a partial unique index — concurrent calls fail fast.
* Credits are consumed when the participant's status flips to
  ``completed``. Screened-out, abandoned, or technically-failed
  participants do not consume credits.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.billing import (
    CreditBalance,
    CreditLedger,
    Plan,
    PlanEntitlement,
    UsageEvent,
    WorkspaceSubscription,
)
from app.models.company import Company
from app.services.billing_plans import (
    ALL_PLANS,
    LEGACY_TIER_TO_PLAN_ID,
    PlanSpec,
)

logger = logging.getLogger(__name__)


# Event types — kept as constants so typos get caught at import time.
EVT_GRANT_INCLUDED = "grant_included"
EVT_GRANT_PURCHASED = "grant_purchased"
EVT_GRANT_ROLLOVER = "grant_rollover"
EVT_CONSUME_INTERVIEW = "consume_interview"
EVT_OVERAGE_INTERVIEW = "overage_interview"
EVT_REFUND_INTERVIEW = "refund_interview"
EVT_REVOKE_PURCHASED = "revoke_purchased"
EVT_ADJUSTMENT_ADMIN = "adjustment_admin"
EVT_EXPIRE_CREDITS = "expire_credits"

# The trial's credit balance needs a ``period_end`` for the "current period"
# query in ``get_active_balance`` to match, but the trial is NOT time-based —
# its credits never expire by calendar. We give it a far-future horizon so the
# balance always reads as "current" without ever surfacing a real expiry date.
TRIAL_CREDIT_HORIZON = timedelta(days=3650)  # ~10 years = "never" for a trial


# ── Public dataclasses ────────────────────────────────────────────────────────


@dataclass
class CanStartResult:
    """Outcome of a pre-interview quota check."""

    allowed: bool
    reason: str  # 'ok' | 'no_subscription' | 'quota_exceeded' | 'past_due' | 'email_not_verified'
    plan_id: str | None = None
    available_credits: int | None = None
    overage_will_apply: bool = False
    is_legacy: bool = False  # if true, caller falls through to feature_gates


# ── Plan + entitlement seeding ───────────────────────────────────────────────


def ensure_plans_seeded(db: Session) -> None:
    """Idempotently sync ``plans`` + ``plan_entitlements`` from the catalogue.

    Safe to call on every API startup. Creates missing rows and updates
    mutable fields (price, included_credits, entitlements) on existing
    rows. Does not delete plans that are no longer in the catalogue —
    we never want to orphan a workspace_subscription.
    """
    for spec in ALL_PLANS:
        existing = db.query(Plan).filter(Plan.id == spec.id).first()
        if existing is None:
            db.add(_plan_from_spec(spec))
        else:
            _update_plan_from_spec(existing, spec)
        _sync_entitlements(db, spec)
    db.commit()


def _plan_from_spec(spec: PlanSpec) -> Plan:
    return Plan(
        id=spec.id,
        public_name=spec.public_name,
        description=spec.description,
        is_public=spec.is_public,
        is_legacy=spec.is_legacy,
        is_custom=spec.is_custom,
        monthly_price_cents=spec.monthly_price_cents,
        annual_price_cents=spec.annual_price_cents,
        currency=spec.currency,
        included_credits=spec.included_credits,
        credit_period=spec.credit_period,
        max_editors=spec.max_editors,
        max_viewers=spec.max_viewers,
        max_active_projects=spec.max_active_projects,
        overage_price_cents=spec.overage_price_cents,
        overage_enabled_default=spec.overage_enabled_default,
        sort_order=spec.sort_order,
    )


def _update_plan_from_spec(plan: Plan, spec: PlanSpec) -> None:
    plan.public_name = spec.public_name
    plan.description = spec.description
    plan.is_public = spec.is_public
    plan.is_legacy = spec.is_legacy
    plan.is_custom = spec.is_custom
    plan.monthly_price_cents = spec.monthly_price_cents
    plan.annual_price_cents = spec.annual_price_cents
    plan.currency = spec.currency
    plan.included_credits = spec.included_credits
    plan.credit_period = spec.credit_period
    plan.max_editors = spec.max_editors
    plan.max_viewers = spec.max_viewers
    plan.max_active_projects = spec.max_active_projects
    plan.overage_price_cents = spec.overage_price_cents
    plan.overage_enabled_default = spec.overage_enabled_default
    plan.sort_order = spec.sort_order
    plan.updated_at = _utcnow()


def _sync_entitlements(db: Session, spec: PlanSpec) -> None:
    existing = {e.key: e for e in db.query(PlanEntitlement).filter(PlanEntitlement.plan_id == spec.id).all()}
    for key, value in spec.entitlements.items():
        row = existing.pop(key, None)
        if row is None:
            db.add(PlanEntitlement(plan_id=spec.id, key=key, value=value))
        elif row.value != value:
            row.value = value
    # Drop entitlements that are no longer in the spec — keeps the table tidy
    # when we deprecate a flag.
    for stale in existing.values():
        db.delete(stale)


# ── Existing-account backfill ────────────────────────────────────────────────


def backfill_legacy_subscriptions(db: Session) -> int:
    """For every Company without a WorkspaceSubscription, create one.

    Maps the existing ``Company.subscription_tier`` to the matching legacy
    plan. Returns the number of subscriptions created (0 on subsequent runs).
    Idempotent and safe to call from startup.
    """
    created = 0
    company_ids_with_sub = {
        row[0] for row in db.query(WorkspaceSubscription.workspace_id).all()
    }
    for company in db.query(Company).all():
        if company.id in company_ids_with_sub:
            continue
        tier = (company.subscription_tier or "starter").lower()
        plan_id = LEGACY_TIER_TO_PLAN_ID.get(tier, "legacy_starter")
        sub = WorkspaceSubscription(
            id=str(uuid.uuid4()),
            workspace_id=company.id,
            plan_id=plan_id,
            status="legacy" if plan_id != "enterprise" else "enterprise_custom",
            billing_interval="legacy",
            stripe_customer_id=company.stripe_customer_id,
            stripe_subscription_id=company.stripe_subscription_id,
            trial_start=None,
            trial_end=company.trial_ends_at,
        )
        db.add(sub)
        created += 1
    db.commit()
    return created


# ── Read helpers ─────────────────────────────────────────────────────────────


def get_current_subscription(db: Session, workspace_id: str) -> WorkspaceSubscription | None:
    """Return the workspace's most recent (active) subscription row."""
    return (
        db.query(WorkspaceSubscription)
        .filter(WorkspaceSubscription.workspace_id == workspace_id)
        .order_by(WorkspaceSubscription.created_at.desc())
        .first()
    )


def get_plan(db: Session, plan_id: str) -> Plan | None:
    return db.query(Plan).filter(Plan.id == plan_id).first()


def get_entitlements(db: Session, workspace_id: str) -> dict[str, Any]:
    """Return the merged entitlement map for a workspace.

    Falls back to the legacy_starter entitlements if the workspace has no
    subscription yet (shouldn't happen post-backfill, but defensive).
    """
    sub = get_current_subscription(db, workspace_id)
    plan_id = sub.plan_id if sub else "legacy_starter"
    rows = db.query(PlanEntitlement).filter(PlanEntitlement.plan_id == plan_id).all()
    return {row.key: row.value for row in rows}


def get_active_balance(db: Session, workspace_id: str) -> CreditBalance | None:
    """Return the credit_balance row covering 'now', or the most recent one."""
    now = _utcnow()
    bal = (
        db.query(CreditBalance)
        .filter(
            CreditBalance.workspace_id == workspace_id,
            CreditBalance.period_start <= now,
            CreditBalance.period_end > now,
        )
        .order_by(CreditBalance.period_start.desc())
        .first()
    )
    if bal is not None:
        return bal
    # No current period — return the latest if any (e.g. expired trial).
    return (
        db.query(CreditBalance)
        .filter(CreditBalance.workspace_id == workspace_id)
        .order_by(CreditBalance.period_end.desc())
        .first()
    )


# ── Quota check (interview start) ────────────────────────────────────────────


def can_start_interview(db: Session, workspace_id: str) -> CanStartResult:
    """Decide whether a new participant may start the interview right now.

    Legacy plans: returns ``allowed=True`` with ``is_legacy=True`` — the
    caller is responsible for running ``feature_gates.require_participant_limit``.

    New plans: checks the active credit balance. Allows the interview if
    ``available > 0``. Allows overage if ``available <= 0`` AND
    ``subscription.overage_enabled``. Otherwise blocks.
    """
    sub = get_current_subscription(db, workspace_id)
    if sub is None:
        return CanStartResult(allowed=False, reason="no_subscription")

    plan = get_plan(db, sub.plan_id)
    if plan is None:
        # Plan was deleted out from under us (shouldn't happen) — fail open
        # for legacy preservation.
        return CanStartResult(allowed=True, reason="ok", plan_id=sub.plan_id, is_legacy=True)

    if plan.is_legacy:
        return CanStartResult(
            allowed=True,
            reason="ok",
            plan_id=plan.id,
            is_legacy=True,
        )

    # Fraud floor — credit consumption is gated on a verified email.
    # Disposable / typo-pad-style accounts that never verify can't
    # spend the 3 free trial credits. Verified accounts (real users
    # who clicked the link) pass through normally.
    from app.models.company import Company  # local import to avoid cycle

    company = db.query(Company).filter(Company.id == workspace_id).first()
    if company is not None and not company.email_verified:
        return CanStartResult(
            allowed=False,
            reason="email_not_verified",
            plan_id=plan.id,
        )

    # Trial expiry used to gate here, but credits already do the gating —
    # an out-of-credits user gets reason="quota_exceeded" regardless of
    # trial state. Calendar trials are a vestige from the old plan model;
    # the credits-native flow lets people sit on unused free credits as
    # long as they want.

    if sub.status in ("canceled", "unpaid"):
        return CanStartResult(allowed=False, reason="past_due", plan_id=plan.id)

    balance = get_active_balance(db, workspace_id)
    available = balance.available if balance else 0

    if available > 0:
        return CanStartResult(
            allowed=True,
            reason="ok",
            plan_id=plan.id,
            available_credits=available,
        )

    # Out of credits — overage path?
    if sub.overage_enabled and plan.overage_price_cents:
        return CanStartResult(
            allowed=True,
            reason="ok",
            plan_id=plan.id,
            available_credits=0,
            overage_will_apply=True,
        )

    return CanStartResult(
        allowed=False,
        reason="quota_exceeded",
        plan_id=plan.id,
        available_credits=available,
    )


# ── Credit consumption (interview completion) ───────────────────────────────


def consume_interview_credit(
    db: Session,
    workspace_id: str,
    participant_id: str,
    project_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CreditLedger | None:
    """Idempotently consume one credit for ``participant_id``.

    Returns:
        The new CreditLedger row on first call.
        ``None`` if a consume/overage row already exists for this
        participant (the idempotency case — quietly do nothing).

    Behaviour:
        - Legacy plan workspaces: no-op (returns None).
        - Available credits > 0: regular consume; ``balance.used_credits += 1``.
        - Available credits <= 0 with overage enabled: overage_interview row;
          ``balance.overage_credits += 1``.
        - Available credits <= 0 with no overage: no-op (returns None) — we
          already let the interview start because ``can_start_interview``
          allowed it; charging at completion would surprise the workspace.
    """
    sub = get_current_subscription(db, workspace_id)
    if sub is None:
        logger.info("consume_interview_credit: no subscription for workspace %s", workspace_id)
        return None

    plan = get_plan(db, sub.plan_id)
    if plan is None or plan.is_legacy:
        return None  # legacy = old participant-limit gate, no credits

    # Idempotency guard — pre-check before insert so concurrent calls fail
    # fast on the application side rather than crashing on the DB constraint.
    existing = (
        db.query(CreditLedger)
        .filter(
            CreditLedger.participant_id == participant_id,
            CreditLedger.event_type.in_((EVT_CONSUME_INTERVIEW, EVT_OVERAGE_INTERVIEW)),
        )
        .first()
    )
    if existing is not None:
        return None

    balance = get_active_balance(db, workspace_id)
    if balance is None:
        # Shouldn't happen on credit plans — we always grant a balance at
        # checkout. Log loudly and bail.
        logger.warning(
            "consume_interview_credit: no balance for workspace=%s plan=%s participant=%s",
            workspace_id, plan.id, participant_id,
        )
        return None

    is_overage = balance.available <= 0
    if is_overage and not sub.overage_enabled:
        # We let the interview start — don't double-back at completion.
        return None

    event_type = EVT_OVERAGE_INTERVIEW if is_overage else EVT_CONSUME_INTERVIEW
    if is_overage:
        balance.overage_credits = (balance.overage_credits or 0) + 1
    else:
        balance.used_credits = (balance.used_credits or 0) + 1

    ledger = CreditLedger(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        balance_id=balance.id,
        participant_id=participant_id,
        project_id=project_id,
        event_type=event_type,
        credits_delta=-1,
        balance_after=balance.available,
        source="interview_completed",
        event_metadata=metadata or {},
    )
    db.add(ledger)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent insert lost the race — the DB-level unique index caught
        # it. Roll back, re-fetch the winning row, return None.
        db.rollback()
        return None

    db.refresh(ledger)

    # Fire-and-forget usage event for analytics dashboards.
    db.add(
        UsageEvent(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            project_id=project_id,
            participant_id=participant_id,
            event_name="credit_consumed" if not is_overage else "credit_overage",
            quantity=1,
            billable=is_overage,
            event_metadata=metadata or {},
        )
    )
    db.commit()

    # PR 3: usage-warning emails. Fires once per period at the 80% and 100%
    # thresholds. Idempotency is enforced by inspecting the usage_events
    # table for an existing matching event in the current period — no
    # spamming the admin if multiple participants complete in quick
    # succession around the threshold boundary.
    try:
        _maybe_send_usage_warning(db, workspace_id, balance)
    except Exception:  # pragma: no cover — never fail consumption on email
        logger.exception("Usage warning trigger failed for workspace %s", workspace_id)

    return ledger


def _maybe_send_usage_warning(db: Session, workspace_id: str, balance: CreditBalance) -> None:
    """Send the 80%/100% warning email if we just crossed the threshold.

    Idempotent: skips the send if a usage_event of the same threshold
    already exists for this period.
    """
    total = (balance.included_credits or 0) + (balance.purchased_credits or 0) + (balance.rollover_credits or 0)
    if total <= 0:
        return
    used = balance.used_credits or 0
    percent = int(round((used / total) * 100))

    threshold: int | None = None
    if percent >= 100:
        threshold = 100
    elif percent >= 80:
        threshold = 80
    if threshold is None:
        return

    event_name = f"usage_warning_{threshold}"
    already_sent = (
        db.query(UsageEvent)
        .filter(
            UsageEvent.workspace_id == workspace_id,
            UsageEvent.event_name == event_name,
            UsageEvent.created_at >= balance.period_start,
        )
        .first()
    )
    if already_sent is not None:
        return

    company = db.query(Company).filter(Company.id == workspace_id).first()
    if company is None or not company.email:
        return
    lang = (company.preferred_language or "en")[:2].lower()
    period_end_str = (
        balance.period_end.strftime("%d %b %Y") if balance.period_end else ""
    )
    billing_url = f"{settings.APP_BASE_URL.rstrip('/')}/account?tab=billing"

    try:
        from app.services.email import send_usage_warning
        send_usage_warning(
            to=company.email,
            percent=percent,
            used=used,
            total=total,
            period_end=period_end_str,
            billing_url=billing_url,
            lang=lang,
        )
    except Exception:
        logger.exception("send_usage_warning failed for %s", company.email)
        return

    db.add(
        UsageEvent(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            event_name=event_name,
            quantity=1,
            billable=False,
            event_metadata={"percent": percent, "used": used, "total": total},
        )
    )
    db.commit()


# ── Initial subscription bootstrap (signup) ──────────────────────────────────


def bootstrap_trial_subscription(db: Session, company: Company) -> WorkspaceSubscription | None:
    """Place ``company`` on the credits-based trial plan with 3 free interview credits.

    The trial is NOT time-based. Access is gated purely by the credit
    balance: a user who exhausts their 3 credits is blocked immediately,
    and a user with credits remaining keeps them indefinitely (no calendar
    expiry). ``trial_end`` is left NULL and the balance gets a far-future
    ``period_end`` (see ``TRIAL_CREDIT_HORIZON``) so nothing surfaces a
    misleading "trial ends" date.

    Behaviour matrix:

    - **No existing subscription** → create a trial sub + balance.
    - **Existing legacy_* sub from the startup backfill** → replace its
      plan + status with trial and create the credit balance. The legacy
      row is updated in place rather than deleted so any inbound Stripe
      webhook with the old subscription id still resolves.
    - **Existing paid sub** (anything not legacy_*, not trial) → no-op.
      We never downgrade a paying customer.
    - **Existing trial sub** → no-op (idempotent for replayed signups).

    Returns the resulting trial subscription, or ``None`` if we declined
    to bootstrap.
    """
    now = _utcnow()
    existing = get_current_subscription(db, company.id)

    if existing is not None and existing.plan_id == "trial":
        return existing  # already trialing, nothing to do
    if existing is not None and not existing.plan_id.startswith("legacy_"):
        # Paid or enterprise — never downgrade.
        return None

    # The trial is NOT time-based — its 3 credits never expire by calendar.
    # We therefore leave ``trial_end`` NULL (no "trial ends" date to surface)
    # and give the credit balance a far-future period_end purely so the
    # ``get_active_balance`` "current period" query keeps matching. Users
    # never see this date; the credits-first UI shows the balance instead.
    trial_period_end = now + TRIAL_CREDIT_HORIZON

    if existing is None:
        sub = WorkspaceSubscription(
            id=str(uuid.uuid4()),
            workspace_id=company.id,
            plan_id="trial",
            status="trialing",
            billing_interval=None,
            trial_start=now,
            trial_end=None,
        )
        db.add(sub)
    else:
        sub = existing
        sub.plan_id = "trial"
        sub.status = "trialing"
        sub.billing_interval = None
        sub.trial_start = now
        sub.trial_end = None
        sub.updated_at = now
    db.flush()

    bal = CreditBalance(
        id=str(uuid.uuid4()),
        workspace_id=company.id,
        subscription_id=sub.id,
        period_start=now,
        period_end=trial_period_end,
        included_credits=3,
    )
    db.add(bal)
    db.flush()

    db.add(
        CreditLedger(
            id=str(uuid.uuid4()),
            workspace_id=company.id,
            balance_id=bal.id,
            event_type=EVT_GRANT_INCLUDED,
            credits_delta=3,
            balance_after=3,
            source="trial_signup",
        )
    )
    db.commit()
    db.refresh(sub)
    return sub


# ── Subscription lifecycle (Stripe webhook handlers) ────────────────────────


def upsert_subscription_from_stripe(
    db: Session,
    *,
    workspace_id: str,
    plan_id: str,
    stripe_customer_id: str,
    stripe_subscription_id: str,
    stripe_price_id: str | None,
    status: str,
    billing_interval: str,
    current_period_start: datetime,
    current_period_end: datetime,
) -> WorkspaceSubscription:
    """Create or update a WorkspaceSubscription from a Stripe webhook event.

    Called from ``customer.subscription.created`` and
    ``customer.subscription.updated`` webhook handlers. Idempotent — if a
    subscription with the same ``stripe_subscription_id`` already exists,
    its mutable fields are updated in place (so plan changes / status
    flips / period rolls all land cleanly). Otherwise a new row is
    inserted and the prior 'legacy' row (if any) is left in place for
    audit history.

    Granting credits for the new period is the caller's job — call
    ``grant_period_credits`` separately after this returns. Splitting them
    keeps the webhook flow readable and lets us re-grant credits without
    re-creating the subscription row on renewals.
    """
    sub = (
        db.query(WorkspaceSubscription)
        .filter(WorkspaceSubscription.stripe_subscription_id == stripe_subscription_id)
        .first()
    )
    if sub is None:
        sub = WorkspaceSubscription(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            plan_id=plan_id,
            status=status,
            billing_interval=billing_interval,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=stripe_price_id,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
        )
        db.add(sub)
    else:
        sub.workspace_id = workspace_id
        sub.plan_id = plan_id
        sub.status = status
        sub.billing_interval = billing_interval
        sub.stripe_customer_id = stripe_customer_id
        sub.stripe_price_id = stripe_price_id
        sub.current_period_start = current_period_start
        sub.current_period_end = current_period_end
        sub.updated_at = _utcnow()
    db.commit()
    db.refresh(sub)
    return sub


def _compute_rollover_from_prior_balance(prior: CreditBalance) -> int:
    """How many credits roll forward from a prior period.

    Policy (V2.2): purchased + prior-rollover credits roll forever; included
    credits expire at period end (use-it-or-lose-it). Consumption is
    attributed to buckets in this order: included → rollover → purchased,
    so unused purchased credits survive even when usage exceeds the
    included grant.
    """
    used = prior.used_credits or 0
    inc  = prior.included_credits or 0
    rol  = prior.rollover_credits or 0
    pur  = prior.purchased_credits or 0

    # Consume included first.
    used_after_included = max(0, used - inc)
    # Then rollover.
    consumed_from_rollover = min(used_after_included, rol)
    used_after_rollover = used_after_included - consumed_from_rollover
    # Finally purchased.
    consumed_from_purchased = min(used_after_rollover, pur)

    unused_rollover  = rol - consumed_from_rollover
    unused_purchased = pur - consumed_from_purchased
    return max(0, unused_rollover + unused_purchased)


def grant_period_credits(
    db: Session,
    subscription: WorkspaceSubscription,
    *,
    source: str = "subscription_renewal",
    metadata: dict[str, Any] | None = None,
) -> CreditBalance | None:
    """Grant ``plan.included_credits`` for the subscription's current period.

    Idempotent per ``(workspace_id, period_start, period_end)`` — re-running
    on a webhook replay returns the existing balance instead of double-
    granting. Returns ``None`` when the plan is legacy or has no credits.

    Also rolls unused **purchased** credits (and prior rollover) forward
    from the most recent prior balance, per the V2.2 policy. Included
    credits expire — they are not carried.
    """
    plan = subscription.plan if subscription.plan_id else None
    if plan is None:
        plan = get_plan(db, subscription.plan_id)
    if plan is None or plan.is_legacy or not plan.included_credits:
        return None
    if subscription.current_period_start is None or subscription.current_period_end is None:
        logger.warning(
            "grant_period_credits: subscription %s has no period bounds", subscription.id
        )
        return None

    existing = (
        db.query(CreditBalance)
        .filter(
            CreditBalance.workspace_id == subscription.workspace_id,
            CreditBalance.period_start == subscription.current_period_start,
            CreditBalance.period_end == subscription.current_period_end,
        )
        .first()
    )
    if existing is not None:
        return existing  # webhook replay — never double-grant

    # Find the most recent prior balance for this workspace. We use
    # ``period_end <= new period_start`` so an exact-touch period chain
    # (common for monthly subs) is treated as adjacent. Anything older
    # than that is still eligible — purchased credits never expire under
    # the V2.2 policy.
    prior = (
        db.query(CreditBalance)
        .filter(
            CreditBalance.workspace_id == subscription.workspace_id,
            CreditBalance.period_end <= subscription.current_period_start,
        )
        .order_by(CreditBalance.period_end.desc())
        .first()
    )
    rollover_amount = _compute_rollover_from_prior_balance(prior) if prior else 0

    balance = CreditBalance(
        id=str(uuid.uuid4()),
        workspace_id=subscription.workspace_id,
        subscription_id=subscription.id,
        period_start=subscription.current_period_start,
        period_end=subscription.current_period_end,
        included_credits=plan.included_credits,
        rollover_credits=rollover_amount,
    )
    db.add(balance)
    db.flush()

    db.add(
        CreditLedger(
            id=str(uuid.uuid4()),
            workspace_id=subscription.workspace_id,
            balance_id=balance.id,
            event_type=EVT_GRANT_INCLUDED,
            credits_delta=plan.included_credits,
            balance_after=plan.included_credits + rollover_amount,
            source=source,
            event_metadata=metadata or {"plan_id": plan.id, "stripe_subscription_id": subscription.stripe_subscription_id},
        )
    )
    if rollover_amount > 0 and prior is not None:
        db.add(
            CreditLedger(
                id=str(uuid.uuid4()),
                workspace_id=subscription.workspace_id,
                balance_id=balance.id,
                event_type=EVT_GRANT_ROLLOVER,
                credits_delta=rollover_amount,
                balance_after=plan.included_credits + rollover_amount,
                source="period_rollover",
                event_metadata={
                    "from_balance_id": prior.id,
                    "from_period_start": prior.period_start.isoformat(),
                    "from_period_end": prior.period_end.isoformat(),
                },
            )
        )
        # Emit an explicit expiry event for the unused-included portion so
        # ledger consumers can reconcile period transitions without having
        # to recompute the policy themselves.
        prior_used = prior.used_credits or 0
        prior_inc = prior.included_credits or 0
        unused_included = max(0, prior_inc - prior_used)
        if unused_included > 0:
            db.add(
                CreditLedger(
                    id=str(uuid.uuid4()),
                    workspace_id=subscription.workspace_id,
                    balance_id=prior.id,
                    event_type=EVT_EXPIRE_CREDITS,
                    credits_delta=-unused_included,
                    balance_after=prior.available,
                    source="period_rollover",
                    event_metadata={"reason": "included_credits_expire_at_period_end"},
                )
            )
    db.commit()
    db.refresh(balance)
    return balance


def grant_purchased_credits(
    db: Session,
    workspace_id: str,
    *,
    credits: int,
    stripe_session_id: str,
    pack_id: str | None = None,
) -> CreditBalance | None:
    """Top up a workspace's active credit balance with a prepaid pack.

    Idempotent per ``stripe_session_id`` — webhook replays don't double
    grant. Returns the updated balance, or None if no active balance
    exists (the workspace would need an active subscription first).
    """
    if credits <= 0:
        return None

    # Idempotency: bail if a grant_purchased ledger row already exists for
    # this Stripe session. Indexed exact match on the dedicated column;
    # LIKE fallback covers rows written before the 0050 migration, where
    # the session id only lives inside the metadata JSON.
    if _find_ledger_by_session(db, workspace_id, EVT_GRANT_PURCHASED, stripe_session_id):
        return billing_get_active_balance_for_workspace(db, workspace_id)

    balance = get_active_balance(db, workspace_id)
    if balance is None:
        logger.warning(
            "grant_purchased_credits: no active balance for workspace %s; pack credit dropped",
            workspace_id,
        )
        return None

    balance.purchased_credits = (balance.purchased_credits or 0) + credits
    balance.updated_at = _utcnow()

    db.add(
        CreditLedger(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            balance_id=balance.id,
            event_type=EVT_GRANT_PURCHASED,
            credits_delta=credits,
            balance_after=balance.available,
            source="stripe_checkout",
            stripe_session_id=stripe_session_id,
            event_metadata={
                "stripe_session_id": stripe_session_id,
                "pack_id": pack_id,
            },
        )
    )
    db.commit()
    db.refresh(balance)
    return balance


def _find_ledger_by_session(
    db: Session, workspace_id: str, event_type: str, stripe_session_id: str
) -> CreditLedger | None:
    """Locate a ledger row for a Stripe checkout session, column-first with a
    JSON-LIKE fallback for pre-0050 rows."""
    if not stripe_session_id:
        return None
    row = (
        db.query(CreditLedger)
        .filter(
            CreditLedger.workspace_id == workspace_id,
            CreditLedger.event_type == event_type,
            CreditLedger.stripe_session_id == stripe_session_id,
        )
        .first()
    )
    if row is not None:
        return row
    return (
        db.query(CreditLedger)
        .filter(
            CreditLedger.workspace_id == workspace_id,
            CreditLedger.event_type == event_type,
            CreditLedger.event_metadata.like(f'%"{stripe_session_id}"%'),
        )
        .first()
    )


def revoke_purchased_credits(
    db: Session,
    workspace_id: str,
    *,
    stripe_session_id: str,
    stripe_charge_id: str | None = None,
    reason: str = "charge_refunded",
) -> CreditBalance | None:
    """Claw back a prepaid credit-pack grant after a Stripe refund.

    Finds the original ``grant_purchased`` row for the checkout session and
    removes the same number of credits from the balance it was granted to.
    Idempotent per session — a second ``charge.refunded`` delivery is a
    no-op because the ``revoke_purchased`` row already exists. The balance
    is clamped so ``purchased_credits`` never goes negative (partial spend
    of the pack means the workspace simply keeps what it already used —
    the delta is recorded in the ledger for support to see).
    """
    grant = _find_ledger_by_session(db, workspace_id, EVT_GRANT_PURCHASED, stripe_session_id)
    if grant is None:
        logger.warning(
            "revoke_purchased_credits: no grant found for session %s (workspace %s)",
            stripe_session_id, workspace_id,
        )
        return None
    if _find_ledger_by_session(db, workspace_id, EVT_REVOKE_PURCHASED, stripe_session_id):
        return billing_get_active_balance_for_workspace(db, workspace_id)

    balance = None
    if grant.balance_id:
        balance = db.query(CreditBalance).filter(CreditBalance.id == grant.balance_id).first()
    if balance is None:
        balance = get_active_balance(db, workspace_id)
    if balance is None:
        logger.warning(
            "revoke_purchased_credits: no balance for workspace %s; ledger-only revoke",
            workspace_id,
        )

    granted = max(0, grant.credits_delta or 0)
    revoked = granted
    if balance is not None:
        revoked = min(granted, max(0, balance.purchased_credits or 0))
        balance.purchased_credits = (balance.purchased_credits or 0) - revoked
        balance.updated_at = _utcnow()

    db.add(
        CreditLedger(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            balance_id=balance.id if balance is not None else None,
            event_type=EVT_REVOKE_PURCHASED,
            credits_delta=-revoked,
            balance_after=balance.available if balance is not None else None,
            source=reason,
            stripe_session_id=stripe_session_id,
            event_metadata={
                "stripe_session_id": stripe_session_id,
                "stripe_charge_id": stripe_charge_id,
                "granted": granted,
                "revoked": revoked,
            },
        )
    )
    db.commit()
    if balance is not None:
        db.refresh(balance)
    return balance


# Alias the existing helper to keep the call-site readable above. The duplicate
# binding is purely cosmetic — both names resolve to the same function.
billing_get_active_balance_for_workspace = get_active_balance


def cancel_subscription(
    db: Session,
    *,
    stripe_subscription_id: str,
    canceled_status: str = "canceled",
) -> WorkspaceSubscription | None:
    """Mark a subscription as canceled in response to ``subscription.deleted``.

    The data isn't deleted — the workspace stays read-only on the cancelled
    plan until a new subscription is created. Existing credit balance is
    preserved so anything in flight can complete.
    """
    sub = (
        db.query(WorkspaceSubscription)
        .filter(WorkspaceSubscription.stripe_subscription_id == stripe_subscription_id)
        .first()
    )
    if sub is None:
        return None
    sub.status = canceled_status
    sub.updated_at = _utcnow()
    db.commit()
    db.refresh(sub)
    return sub


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
