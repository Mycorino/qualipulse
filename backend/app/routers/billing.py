"""Billing endpoints — credits-aware, with legacy-tier passthrough.

Surface area
------------
- ``GET  /billing/plans``    — public plan catalogue (legacy + new).
- ``GET  /billing/status``   — current subscription + entitlements.
- ``GET  /billing/usage``    — credit balance for credits-based plans.
- ``POST /billing/checkout`` — Stripe Checkout, accepts legacy tiers OR
  new credit plans (pass ``billing_interval`` for credit plans).
- ``POST /billing/portal``   — Stripe Customer Portal.
- ``POST /billing/webhook``  — Stripe webhook handler (single endpoint
  for every event; idempotent per Stripe event id).

The webhook handles both subscription tracks:
- For new credit plans (resolved via ``plan_id_for_stripe_price``) it
  calls ``BillingService.upsert_subscription_from_stripe`` and
  ``grant_period_credits``.
- For legacy tier price IDs it falls back to the prior behaviour
  (mutates ``Company.subscription_tier`` directly).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.models.affiliate import AffiliateReferral
from app.models.billing import Plan, PlanEntitlement
from app.models.company import Company
from app.services import billing_service
from app.services.billing_plans import (
    billing_interval_for_stripe_price,
    plan_id_for_stripe_price,
    stripe_price_id_for,
)
from app.services.feature_gates import TIER_LIMITS, get_limits
from app.services.survey_quotas import get_status as get_survey_quota_status

logger = logging.getLogger("auto_interview.billing")
router = APIRouter(prefix="/billing", tags=["billing"])


# ── Request / response shapes ─────────────────────────────────────────────────


class CheckoutRequest(BaseModel):
    """Either a legacy tier id (`"team"`, `"lab"`) or a new plan id
    (`"exploration"`, `"team"`, `"agency"`). For new plans pass
    ``billing_interval`` (`"monthly"` | `"annual"`); for legacy tiers it's
    ignored."""

    tier: str | None = None  # legacy alias
    plan_id: str | None = None  # preferred field name
    billing_interval: str = "monthly"
    success_url: str
    cancel_url: str

    def resolve_plan_id(self) -> str:
        return self.plan_id or self.tier or ""


class PortalRequest(BaseModel):
    return_url: str


def _validate_redirect_url(url: str, field: str) -> str:
    """Reject Stripe redirect URLs that don't match our APP_BASE_URL host.

    Without this, an attacker could POST /billing/checkout with a
    success_url pointing at their own domain and harvest ?session_id query
    params to phish users post-payment.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail=f"Invalid {field}")
    expected = urlparse(settings.APP_BASE_URL)
    if expected.netloc and parsed.netloc != expected.netloc:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must match the configured app host",
        )
    return url


# ── Public plan catalogue ─────────────────────────────────────────────────────


@router.get("/plans")
def list_plans(db: Session = Depends(get_db)):
    """Return the public plan catalogue.

    Reads the live ``plans`` + ``plan_entitlements`` tables (kept in sync
    with ``services/billing_plans.py`` on every startup). Excludes
    ``is_legacy`` plans by default — legacy plans only show up via
    ``/billing/status`` for accounts already on them.
    """
    plans = (
        db.query(Plan)
        .filter(Plan.is_public == True, Plan.is_legacy == False)  # noqa: E712
        .order_by(Plan.sort_order)
        .all()
    )
    by_plan_id: dict[str, dict] = {}
    ents = db.query(PlanEntitlement).filter(
        PlanEntitlement.plan_id.in_([p.id for p in plans])
    ).all()
    for e in ents:
        by_plan_id.setdefault(e.plan_id, {})[e.key] = e.value

    return [
        {
            "id": p.id,
            "name": p.public_name,
            "description": p.description,
            "monthly_price_cents": p.monthly_price_cents,
            "annual_price_cents": p.annual_price_cents,
            "currency": p.currency,
            "included_credits": p.included_credits,
            "credit_period": p.credit_period,
            "max_editors": p.max_editors,
            "max_viewers": p.max_viewers,
            "max_active_projects": p.max_active_projects,
            "overage_price_cents": p.overage_price_cents,
            "is_custom": p.is_custom,
            "entitlements": by_plan_id.get(p.id, {}),
        }
        for p in plans
    ]


# ── Per-workspace status / usage ─────────────────────────────────────────────


@router.get("/status")
def billing_status(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Return current subscription state.

    Always returns the legacy tier shape (``tier``, ``limits``, ``usage``)
    so existing frontend callers keep working. For accounts on credit-
    based plans, ``plan`` and ``credits`` blocks are populated alongside.
    """
    sub = billing_service.get_current_subscription(db, company.id)
    plan = billing_service.get_plan(db, sub.plan_id) if sub else None
    legacy_limits = get_limits(company.subscription_tier)

    response: dict = {
        # Legacy fields (kept for AccountSettings.tsx compatibility)
        "tier": company.subscription_tier,
        "tier_name": legacy_limits.name,
        "status": company.subscription_status,
        "stripe_customer_id": company.stripe_customer_id,
        "trial_ends_at": company.trial_ends_at.isoformat() if company.trial_ends_at else None,
        "limits": {
            "max_projects": legacy_limits.max_projects,
            "max_participants_per_project": legacy_limits.max_participants_per_project,
            "ai_analysis": legacy_limits.ai_analysis,
            "export_csv": legacy_limits.export_csv,
            "team_members": legacy_limits.team_members,
        },
        "usage": {
            "interview_count": company.interview_count,
            "storage_bytes": company.storage_bytes,
        },
        # New credits-aware fields. None for accounts that haven't been
        # backfilled yet — frontend treats absent fields as "fall back to
        # the legacy tier shape".
        "plan": None,
        "credits": None,
    }

    if sub and plan:
        # The trial is not time-based — never surface a trial-end date for it,
        # even if a legacy row still carries one. (Pre-credits accounts had
        # trial_end = signup + 14d; suppressing it here fixes the stale
        # "Trial ends 31/05/2026" the account page showed.)
        is_trial = plan.credit_period == "trial_total"
        trial_end_display = (
            None if is_trial else (sub.trial_end.isoformat() if sub.trial_end else None)
        )
        response["plan"] = {
            "id": plan.id,
            "name": plan.public_name,
            "is_legacy": plan.is_legacy,
            "is_custom": plan.is_custom,
            "is_trial": is_trial,
            "monthly_price_cents": plan.monthly_price_cents,
            "annual_price_cents": plan.annual_price_cents,
            "billing_interval": sub.billing_interval,
            "subscription_status": sub.status,
            "current_period_start": sub.current_period_start.isoformat() if sub.current_period_start else None,
            "current_period_end": sub.current_period_end.isoformat() if sub.current_period_end else None,
            "trial_end": trial_end_display,
            "cancel_at_period_end": sub.cancel_at_period_end,
            "overage_enabled": sub.overage_enabled,
        }
        balance = billing_service.get_active_balance(db, company.id)
        if balance and not plan.is_legacy:
            response["credits"] = _credits_payload(balance, hide_period=is_trial)

        # Canonical display block — ONE source of truth for credit-native
        # accounts so the UI stops mixing the legacy tier (e.g. "Starter
        # active") with the subscription truth (e.g. "Trial trialing").
        # Legacy-plan accounts keep using the top-level tier shape.
        if not plan.is_legacy:
            response["display"] = {
                "plan_name": plan.public_name,
                "is_trial": is_trial,
                # For a trial we present "active" rather than the internal
                # "trialing" status — there's nothing time-bound to convey.
                "status": "active" if is_trial else sub.status,
                "show_trial_end": False if is_trial else bool(sub.trial_end),
            }
    return response


@router.get("/usage")
def billing_usage(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Return the current period credit balance.

    Returns 404 for legacy-plan workspaces — the frontend should fall back
    to the participant-count usage exposed in ``/billing/status``.
    """
    sub = billing_service.get_current_subscription(db, company.id)
    plan = billing_service.get_plan(db, sub.plan_id) if sub else None
    if not plan or plan.is_legacy:
        raise HTTPException(
            status_code=404,
            detail={"code": "no_credit_plan", "message": "Workspace is on a legacy plan."},
        )
    balance = billing_service.get_active_balance(db, company.id)
    if balance is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "no_balance", "message": "No active credit balance."},
        )
    return _credits_payload(balance, hide_period=(plan.credit_period == "trial_total"))


def _credits_payload(balance, hide_period: bool = False) -> dict:
    """Serialize a credit balance.

    ``hide_period=True`` (trial plans) nulls out the period dates so the UI
    never renders a "Period ends …" line for credits that don't expire by
    calendar. The far-future trial horizon is an internal query artifact, not
    a user-facing date.
    """
    return {
        "included_credits":  balance.included_credits or 0,
        "purchased_credits": balance.purchased_credits or 0,
        "rollover_credits":  balance.rollover_credits or 0,
        "used_credits":      balance.used_credits or 0,
        "overage_credits":   balance.overage_credits or 0,
        "available_credits": balance.available,
        "period_start":      None if hide_period else (balance.period_start.isoformat() if balance.period_start else None),
        "period_end":        None if hide_period else (balance.period_end.isoformat() if balance.period_end else None),
    }


# ── Stripe Checkout ──────────────────────────────────────────────────────────


@router.post("/checkout")
def create_checkout_session(
    body: CheckoutRequest,
    company: Company = Depends(get_current_company),
):
    """Create a Stripe Checkout session for legacy tier or new credit plan.

    Body fields:
      ``plan_id`` (preferred) — one of ``exploration`` | ``team`` |
      ``agency`` for new plans, or ``legacy_team`` | ``legacy_lab``.
      ``tier`` — legacy alias kept for backwards-compat with the existing
      AccountSettings UI.
      ``billing_interval`` — ``monthly`` | ``annual`` (ignored for legacy).
    """
    stripe_key = settings.STRIPE_SECRET_KEY
    if not stripe_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured. Contact support.",
        )

    plan_id = body.resolve_plan_id()
    if not plan_id:
        raise HTTPException(status_code=400, detail="plan_id (or tier) is required")

    interval = body.billing_interval.lower()
    if interval not in ("monthly", "annual"):
        raise HTTPException(status_code=400, detail="billing_interval must be monthly or annual")

    price_id = stripe_price_id_for(plan_id, interval)
    if not price_id:
        # Legacy compat: caller might be sending a legacy tier name.
        # IMPORTANT: do NOT include 'team' here — it collides with the new
        # credits-based Team plan (€299/mo). Only map aliases that are
        # unambiguously legacy.
        legacy_map = {
            "lab":     stripe_price_id_for("legacy_lab",  "monthly"),
            "starter": stripe_price_id_for("legacy_team", "monthly"),  # legacy alias
            "pro":     stripe_price_id_for("legacy_lab",  "monthly"),
        }
        price_id = legacy_map.get(plan_id)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"No Stripe price configured for plan_id={plan_id} interval={interval}",
        )

    try:
        import stripe  # type: ignore
        stripe.api_key = stripe_key

        session_kwargs: dict = dict(
            customer_email=company.email,
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=_validate_redirect_url(body.success_url, "success_url"),
            cancel_url=_validate_redirect_url(body.cancel_url, "cancel_url"),
            # Billing address is required for B2B invoicing + VAT
            # determination; Stripe stores it on the customer/invoice.
            billing_address_collection="required",
            metadata={
                "company_id": company.id,
                "workspace_id": company.id,
                "plan_id": plan_id,
                "billing_interval": interval,
            },
        )
        if settings.STRIPE_AUTOMATIC_TAX:
            session_kwargs["automatic_tax"] = {"enabled": True}
            session_kwargs["tax_id_collection"] = {"enabled": True}
        session = stripe.checkout.Session.create(**session_kwargs)
        return {"checkout_url": session.url}
    except ImportError:
        raise HTTPException(status_code=503, detail="Stripe library not installed")
    except Exception as e:  # pragma: no cover — Stripe SDK errors
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


class OverageToggleRequest(BaseModel):
    overage_enabled: bool


@router.patch("/overage")
def update_overage_setting(
    body: OverageToggleRequest,
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Toggle automatic overage billing for the workspace.

    When enabled, interviews can start even after the credit balance is
    exhausted; each extra interview is charged at the plan's
    ``overage_price_cents`` rate (billed at the end of the period via
    Stripe metered billing — wired in PR 3+ but not yet enforced).

    Unavailable for legacy plans.
    """
    sub = billing_service.get_current_subscription(db, company.id)
    plan = billing_service.get_plan(db, sub.plan_id) if sub else None
    if not sub or not plan or plan.is_legacy:
        raise HTTPException(status_code=400, detail="Overage is not available on this plan.")
    sub.overage_enabled = body.overage_enabled
    sub.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(sub)
    return {"overage_enabled": sub.overage_enabled}


@router.get("/credit-packs")
def list_credit_packs():
    """Return the available prepaid credit packs (PR 3)."""
    from app.services.billing_plans import CREDIT_PACKS, stripe_price_id_for_pack

    return [
        {
            "id": p.id,
            "name": p.public_name,
            "credits": p.credits,
            "price_cents": p.price_cents,
            "currency": p.currency,
            "description": p.description,
            "available": stripe_price_id_for_pack(p.id) is not None,
        }
        for p in CREDIT_PACKS
    ]


class CreditPackCheckoutRequest(BaseModel):
    pack_id: str = Field(..., description="One of pack_25 | pack_50 | pack_100")
    success_url: str
    cancel_url: str


@router.post("/checkout/credits")
def create_credit_pack_checkout(
    body: CreditPackCheckoutRequest,
    company: Company = Depends(get_current_company),
):
    """Create a one-time Stripe Checkout for a prepaid credit pack."""
    from app.services.billing_plans import get_credit_pack, stripe_price_id_for_pack

    stripe_key = settings.STRIPE_SECRET_KEY
    if not stripe_key:
        raise HTTPException(status_code=503, detail="Billing is not configured.")

    pack = get_credit_pack(body.pack_id)
    if pack is None:
        raise HTTPException(status_code=400, detail=f"Unknown credit pack: {body.pack_id}")
    price_id = stripe_price_id_for_pack(pack.id)
    if not price_id:
        raise HTTPException(
            status_code=400,
            detail=f"No Stripe price configured for {pack.id}",
        )

    try:
        import stripe  # type: ignore
        stripe.api_key = stripe_key

        pack_metadata = {
            "company_id": company.id,
            "workspace_id": company.id,
            "pack_id": pack.id,
            "credits": str(pack.credits),
        }
        session_kwargs: dict = dict(
            customer_email=company.email,
            payment_method_types=["card"],
            mode="payment",  # one-time, not subscription
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=_validate_redirect_url(body.success_url, "success_url"),
            cancel_url=_validate_redirect_url(body.cancel_url, "cancel_url"),
            billing_address_collection="required",
            metadata=pack_metadata,
            # Copy the workspace metadata onto the PaymentIntent (Stripe
            # propagates it to the charge) so a later charge.refunded
            # webhook can resolve the workspace without an API lookup.
            payment_intent_data={"metadata": pack_metadata},
        )
        if settings.STRIPE_AUTOMATIC_TAX:
            session_kwargs["automatic_tax"] = {"enabled": True}
            session_kwargs["tax_id_collection"] = {"enabled": True}
            # tax_id_collection in payment mode requires a Customer object.
            session_kwargs["customer_creation"] = "always"
        session = stripe.checkout.Session.create(**session_kwargs)
        return {"checkout_url": session.url}
    except ImportError:
        raise HTTPException(status_code=503, detail="Stripe library not installed")
    except Exception as e:  # pragma: no cover
        logger.error("Stripe credit-pack checkout error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create credit-pack checkout")


@router.post("/portal")
def create_portal_session(
    body: PortalRequest,
    company: Company = Depends(get_current_company),
):
    stripe_key = settings.STRIPE_SECRET_KEY
    if not stripe_key or not company.stripe_customer_id:
        raise HTTPException(status_code=503, detail="Billing portal not available")
    try:
        import stripe  # type: ignore
        stripe.api_key = stripe_key
        session = stripe.billing_portal.Session.create(
            customer=company.stripe_customer_id,
            return_url=_validate_redirect_url(body.return_url, "return_url"),
        )
        return {"portal_url": session.url}
    except Exception as e:  # pragma: no cover
        logger.error("Stripe portal error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to open billing portal")


# ── Webhook ──────────────────────────────────────────────────────────────────


# ── Sprint 12: Survey quota status ───────────────────────────────────


class SurveyQuotaResponse(BaseModel):
    """Workspace-facing snapshot of survey quotas. Used by the dashboard
    nudge banner and the Study Overview progress card."""

    responses_used: int
    responses_cap: int | None
    surveys_active: int
    surveys_cap: int | None
    questions_per_survey_cap: int | None
    period_start: str
    period_end: str | None
    is_over_response_cap: bool
    is_near_response_cap: bool
    is_over_surveys_cap: bool


@router.get("/survey-quota", response_model=SurveyQuotaResponse)
def get_survey_quota(
    db: Session = Depends(get_db),
    company: Company = Depends(get_current_company),
) -> SurveyQuotaResponse:
    """Returns the current survey-quota status for the workspace.

    Drives:
      - Dashboard nudge banner when usage ≥ 80% or over cap
      - Study Overview quota chip
      - Future pricing-page logged-in context

    Surveys do NOT touch the credit ledger — this is pure quota math.
    """

    status = get_survey_quota_status(db, company)
    return SurveyQuotaResponse(
        responses_used=status.responses_used,
        responses_cap=status.responses_cap,
        surveys_active=status.surveys_active,
        surveys_cap=status.surveys_cap,
        questions_per_survey_cap=status.questions_per_survey_cap,
        period_start=status.period_start.isoformat(),
        period_end=status.period_end.isoformat() if status.period_end else None,
        is_over_response_cap=status.is_over_response_cap,
        is_near_response_cap=status.is_near_response_cap,
        is_over_surveys_cap=status.is_over_surveys_cap,
    )


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle Stripe webhook events for both legacy tiers and credit plans."""
    stripe_key = settings.STRIPE_SECRET_KEY
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    if not stripe_key:
        raise HTTPException(status_code=503, detail="Billing not configured")
    if not webhook_secret:
        raise HTTPException(status_code=500, detail="Stripe webhook secret not configured")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        import stripe  # type: ignore
        stripe.api_key = stripe_key
        event = stripe.Webhook.construct_event(payload, sig, webhook_secret)
    except Exception as e:
        logger.error("Webhook error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook payload")

    event_type = event["type"]
    logger.info("Stripe webhook: %s", event_type)

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        _handle_subscription_event(db, event_type, event["data"]["object"])
    elif event_type == "customer.subscription.deleted":
        _handle_subscription_deleted(db, event["data"]["object"])
    elif event_type == "invoice.payment_succeeded":
        _handle_invoice_payment_succeeded(db, event["data"]["object"])
    elif event_type == "invoice.payment_failed":
        _handle_invoice_payment_failed(db, event["data"]["object"])
    elif event_type == "checkout.session.completed":
        _handle_checkout_session_completed(db, event["data"]["object"])
    elif event_type == "charge.refunded":
        _handle_charge_refunded(db, event["data"]["object"])
    elif event_type in ("charge.dispute.created", "charge.dispute.updated"):
        _handle_charge_dispute(db, event_type, event["data"]["object"])
    return {"received": True}


def _handle_checkout_session_completed(db: Session, session: dict) -> None:
    """Fulfilment for one-time prepaid credit-pack checkouts.

    Subscription checkouts also fire this event but we already handle
    them via ``customer.subscription.created`` — short-circuit when the
    session mode isn't ``payment``.
    """
    if session.get("mode") != "payment":
        return
    workspace_id = session.get("metadata", {}).get("workspace_id") or session.get("metadata", {}).get("company_id")
    if not workspace_id:
        logger.warning("Credit pack checkout session %s missing workspace metadata", session.get("id"))
        return
    pack_id = session.get("metadata", {}).get("pack_id")
    credits_str = session.get("metadata", {}).get("credits")
    try:
        credits = int(credits_str) if credits_str else 0
    except (TypeError, ValueError):
        credits = 0
    # Defensive: if metadata didn't carry the credits, look up by line item.
    if credits <= 0:
        from app.services.billing_plans import credit_pack_for_stripe_price
        line_items = session.get("display_items") or session.get("line_items", {}).get("data", [])
        for line in line_items:
            price_id = (line.get("price", {}) or {}).get("id", "")
            pack = credit_pack_for_stripe_price(price_id)
            if pack:
                credits = pack.credits
                pack_id = pack.id
                break
    if credits <= 0:
        logger.warning("Credit pack checkout session %s resolved zero credits", session.get("id"))
        return

    billing_service.grant_purchased_credits(
        db,
        workspace_id,
        credits=credits,
        stripe_session_id=session.get("id", ""),
        pack_id=pack_id,
    )

    # V4 paywall — a credit-pack purchase counts as "has paid" for
    # the purposes of unlocking historical transcripts. Pack buyers
    # get the same unlock-everything treatment as subscribers.
    from app.models.company import Company

    company = db.query(Company).filter(Company.id == workspace_id).first()
    if company is not None and not company.has_ever_paid:
        company.has_ever_paid = True
        db.commit()


def _handle_subscription_event(db: Session, event_type: str, sub: dict) -> None:
    """Apply a Stripe subscription create/update event to our state.

    Routing:
    - If the price id resolves to a credit plan via ``plan_id_for_stripe_price``,
      upsert the WorkspaceSubscription + grant period credits.
    - Otherwise (legacy price id or unknown) fall through to the legacy
      tier mutation on Company so existing customers keep working.
    """
    workspace_id = sub.get("metadata", {}).get("workspace_id") or sub.get("metadata", {}).get("company_id")
    if not workspace_id:
        logger.warning("Stripe sub event with no workspace_id metadata: %s", sub.get("id"))
        return
    company = db.query(Company).filter(Company.id == workspace_id).first()
    if not company:
        logger.warning("Unknown workspace_id %s in Stripe sub event", workspace_id)
        return

    price_id = (
        sub.get("items", {}).get("data", [{}])[0].get("price", {}).get("id", "")
        if sub.get("items") else ""
    )
    plan_id = plan_id_for_stripe_price(price_id)

    # Legacy fallback: keep prior behaviour for existing customers.
    if plan_id is None or plan_id.startswith("legacy_"):
        legacy_tier_map = {
            settings.STRIPE_PRICE_STARTER: "team",   # legacy mapping kept as-was
            settings.STRIPE_PRICE_PRO:     "lab",
        }
        new_tier = legacy_tier_map.get(price_id)
        if new_tier:
            company.subscription_tier = new_tier
        company.subscription_status = sub.get("status", company.subscription_status)
        company.stripe_subscription_id = sub.get("id")
        if sub.get("customer"):
            company.stripe_customer_id = sub["customer"]
        db.commit()
        if event_type == "customer.subscription.created":
            _track_affiliate_conversion(db, workspace_id, sub)
        return

    # Credit-based plan path.
    period_start = _ts(sub.get("current_period_start"))
    period_end = _ts(sub.get("current_period_end"))
    interval = billing_interval_for_stripe_price(price_id)

    subscription = billing_service.upsert_subscription_from_stripe(
        db,
        workspace_id=workspace_id,
        plan_id=plan_id,
        stripe_customer_id=sub.get("customer", "") or "",
        stripe_subscription_id=sub.get("id", "") or "",
        stripe_price_id=price_id or None,
        status=sub.get("status", "active"),
        billing_interval=interval,
        current_period_start=period_start,
        current_period_end=period_end,
    )
    billing_service.grant_period_credits(
        db,
        subscription,
        source="stripe_webhook",
        metadata={"event_type": event_type, "stripe_subscription_id": subscription.stripe_subscription_id},
    )

    # Mirror onto Company.* so legacy code paths that read these fields
    # continue to work during the rollout (admin panel, AccountSettings).
    company.stripe_customer_id = subscription.stripe_customer_id or company.stripe_customer_id
    company.stripe_subscription_id = subscription.stripe_subscription_id
    company.subscription_status = subscription.status
    # V4 paywall — sticky flag for "has ever paid." Survives cancellation
    # so ex-customers don't lose read-only access to their historical
    # transcripts. Set once, never reset.
    if subscription.status in ("active", "past_due"):
        company.has_ever_paid = True
    db.commit()

    if event_type == "customer.subscription.created":
        _track_affiliate_conversion(db, workspace_id, sub)
        try:
            from app.services.analytics import emit_event
            emit_event(
                "paid_converted",
                company=company,
                plan_id=subscription.plan_id if subscription else None,
                billing_interval=subscription.billing_interval if subscription else None,
                stripe_subscription_id=subscription.stripe_subscription_id if subscription else None,
            )
        except Exception:
            pass


def _handle_subscription_deleted(db: Session, sub: dict) -> None:
    sub_id = sub.get("id", "")
    cancelled = billing_service.cancel_subscription(
        db, stripe_subscription_id=sub_id, canceled_status="canceled"
    )
    if cancelled is None:
        # Legacy fallback — flip the company tier
        company_id = sub.get("metadata", {}).get("company_id")
        if company_id:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                company.subscription_tier = "starter"
                company.subscription_status = "canceled"
                db.commit()
    else:
        company = db.query(Company).filter(Company.id == cancelled.workspace_id).first()
        if company:
            company.subscription_status = "canceled"
            db.commit()


def _handle_invoice_payment_succeeded(db: Session, invoice: dict) -> None:
    """On renewal invoices, refresh the subscription's period bounds and
    grant the next period's credits. ``customer.subscription.updated``
    usually fires alongside, but this handler is the safety net."""
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return
    from app.models.billing import WorkspaceSubscription
    sub_row = (
        db.query(WorkspaceSubscription)
        .filter(WorkspaceSubscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if sub_row is None:
        return
    # Update period bounds from the invoice's line items if present.
    lines = invoice.get("lines", {}).get("data", [])
    if lines:
        period = lines[0].get("period", {})
        new_start = _ts(period.get("start"))
        new_end = _ts(period.get("end"))
        if new_start and new_end:
            sub_row.current_period_start = new_start
            sub_row.current_period_end = new_end
            db.commit()
            db.refresh(sub_row)
    billing_service.grant_period_credits(
        db, sub_row, source="invoice_payment_succeeded",
        metadata={"stripe_invoice_id": invoice.get("id")},
    )


def _handle_invoice_payment_failed(db: Session, invoice: dict) -> None:
    """A renewal charge failed — flip the subscription to past_due so
    ``can_start_interview`` stops admitting new interviews. Stripe retries
    per its dunning schedule; a later ``invoice.payment_succeeded`` (or
    ``customer.subscription.updated``) restores the active status."""
    stripe_sub_id = invoice.get("subscription")
    if not stripe_sub_id:
        return
    from app.models.billing import WorkspaceSubscription
    sub_row = (
        db.query(WorkspaceSubscription)
        .filter(WorkspaceSubscription.stripe_subscription_id == stripe_sub_id)
        .first()
    )
    if sub_row is None:
        return
    if sub_row.status not in ("canceled", "unpaid"):
        sub_row.status = "past_due"
        sub_row.updated_at = datetime.utcnow()
    company = db.query(Company).filter(Company.id == sub_row.workspace_id).first()
    if company:
        company.subscription_status = "past_due"
    db.commit()
    logger.warning(
        "Stripe invoice payment FAILED for subscription %s (workspace %s) — marked past_due",
        stripe_sub_id, sub_row.workspace_id,
    )


def _workspace_id_for_charge(db: Session, charge: dict) -> str | None:
    """Best-effort resolution of the workspace behind a Stripe charge.

    Order: charge metadata (credit-pack PaymentIntents carry it since we set
    ``payment_intent_data.metadata`` at checkout) → the Stripe customer id
    on any WorkspaceSubscription / Company row.
    """
    meta = charge.get("metadata") or {}
    workspace_id = meta.get("workspace_id") or meta.get("company_id")
    if workspace_id:
        return workspace_id
    customer_id = charge.get("customer")
    if not customer_id:
        return None
    from app.models.billing import WorkspaceSubscription
    sub_row = (
        db.query(WorkspaceSubscription)
        .filter(WorkspaceSubscription.stripe_customer_id == customer_id)
        .first()
    )
    if sub_row is not None:
        return sub_row.workspace_id
    company = db.query(Company).filter(Company.stripe_customer_id == customer_id).first()
    return company.id if company else None


def _handle_charge_refunded(db: Session, charge: dict) -> None:
    """Keep credit balances in sync when a payment is refunded in Stripe.

    Credit-pack refunds claw the granted credits back (idempotent per
    checkout session). Subscription-invoice refunds are recorded as a
    UsageEvent for admin follow-up — clawing back period credits
    automatically would strand in-flight interviews, so support decides
    via the admin credit-adjust endpoint.
    """
    workspace_id = _workspace_id_for_charge(db, charge)
    if not workspace_id:
        logger.warning("charge.refunded %s: could not resolve workspace", charge.get("id"))
        return

    if charge.get("invoice"):
        # Subscription payment refund — surface it, don't auto-clawback.
        from app.models.billing import UsageEvent
        db.add(UsageEvent(
            workspace_id=workspace_id,
            event_name="stripe_subscription_refund",
            billable=False,
            event_metadata={
                "stripe_charge_id": charge.get("id"),
                "stripe_invoice_id": charge.get("invoice"),
                "amount_refunded": charge.get("amount_refunded"),
                "currency": charge.get("currency"),
            },
        ))
        db.commit()
        logger.warning(
            "Stripe SUBSCRIPTION refund on workspace %s (charge %s, %s %s) — "
            "review credits via admin adjust",
            workspace_id, charge.get("id"),
            charge.get("amount_refunded"), charge.get("currency"),
        )
        return

    # One-time payment (credit pack): find the checkout session and revoke.
    session_id = (charge.get("metadata") or {}).get("checkout_session_id")
    if not session_id:
        payment_intent = charge.get("payment_intent")
        if payment_intent and settings.STRIPE_SECRET_KEY:
            try:
                import stripe  # type: ignore
                stripe.api_key = settings.STRIPE_SECRET_KEY
                sessions = stripe.checkout.Session.list(payment_intent=payment_intent, limit=1)
                if sessions.data:
                    session_id = sessions.data[0].id
            except Exception:  # pragma: no cover — network fallback only
                logger.exception("charge.refunded: session lookup failed for %s", charge.get("id"))
    if not session_id:
        logger.warning(
            "charge.refunded %s: no checkout session resolvable — manual review needed "
            "(workspace %s)", charge.get("id"), workspace_id,
        )
        return

    billing_service.revoke_purchased_credits(
        db,
        workspace_id,
        stripe_session_id=session_id,
        stripe_charge_id=charge.get("id"),
    )
    logger.warning(
        "Stripe credit-pack refund processed: workspace %s session %s charge %s",
        workspace_id, session_id, charge.get("id"),
    )


def _handle_charge_dispute(db: Session, event_type: str, dispute: dict) -> None:
    """Record chargebacks so they're visible to admins — no automatic
    punitive action (Stripe freezes the funds; support investigates)."""
    charge = dispute.get("charge")
    workspace_id = _workspace_id_for_charge(
        db, {"id": charge, "metadata": dispute.get("metadata") or {},
             "customer": dispute.get("customer")},
    )
    from app.models.billing import UsageEvent
    if workspace_id:
        db.add(UsageEvent(
            workspace_id=workspace_id,
            event_name="stripe_dispute",
            billable=False,
            event_metadata={
                "stripe_dispute_id": dispute.get("id"),
                "stripe_charge_id": charge,
                "status": dispute.get("status"),
                "reason": dispute.get("reason"),
                "amount": dispute.get("amount"),
                "currency": dispute.get("currency"),
                "event_type": event_type,
            },
        ))
        db.commit()
    logger.warning(
        "Stripe DISPUTE %s: charge=%s workspace=%s reason=%s status=%s amount=%s %s",
        dispute.get("id"), charge, workspace_id or "?", dispute.get("reason"),
        dispute.get("status"), dispute.get("amount"), dispute.get("currency"),
    )


def _track_affiliate_conversion(db: Session, workspace_id: str, sub: dict) -> None:
    """Replicate the prior affiliate-conversion side effect."""
    referral = (
        db.query(AffiliateReferral)
        .filter(AffiliateReferral.referred_company_id == workspace_id)
        .first()
    )
    if not referral:
        return
    referral.status = "converted"
    referral.converted_at = datetime.utcnow()
    affiliate = referral.affiliate
    if affiliate and sub.get("items", {}).get("data"):
        item = sub["items"]["data"][0]
        unit_amount = item.get("price", {}).get("unit_amount_decimal")
        if unit_amount:
            subscription_amount = float(unit_amount) / 100.0
            commission = (affiliate.commission_pct / 100.0) * subscription_amount
            referral.commission_amount = commission
            affiliate.total_earned += commission
    db.commit()


def _ts(v):
    """Stripe sends Unix timestamps; convert to naive UTC datetimes."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, tz=timezone.utc).replace(tzinfo=None)
    return None
