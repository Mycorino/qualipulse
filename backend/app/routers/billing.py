"""
Billing routes — Stripe integration scaffold.
Set STRIPE_SECRET_KEY in .env to enable payments.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_current_company, get_db
from app.models.company import Company
from app.services.feature_gates import TIER_LIMITS, get_limits

logger = logging.getLogger("auto_interview.billing")
router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutRequest(BaseModel):
    tier: str  # "team" | "lab" | "enterprise"
    success_url: str
    cancel_url: str


class PortalRequest(BaseModel):
    return_url: str


@router.get("/plans")
def list_plans():
    """Return all available subscription tiers and their limits."""
    # Only return canonical tiers, not legacy aliases (free/starter/pro)
    canonical_tiers = ("solo", "team", "lab", "enterprise")
    return [
        {
            "id": tier_id,
            "name": TIER_LIMITS[tier_id].name,
            "price_monthly_usd": TIER_LIMITS[tier_id].price_monthly_usd,
            "max_projects": TIER_LIMITS[tier_id].max_projects,
            "max_participants_per_project": TIER_LIMITS[tier_id].max_participants_per_project,
            "ai_analysis": TIER_LIMITS[tier_id].ai_analysis,
            "export_csv": TIER_LIMITS[tier_id].export_csv,
            "custom_branding": TIER_LIMITS[tier_id].custom_branding,
            "team_members": TIER_LIMITS[tier_id].team_members,
        }
        for tier_id in canonical_tiers
    ]


@router.get("/status")
def billing_status(
    company: Company = Depends(get_current_company),
    db: Session = Depends(get_db),
):
    """Return current subscription status for the authenticated company."""
    limits = get_limits(company.subscription_tier)
    return {
        "tier": company.subscription_tier,
        "tier_name": limits.name,
        "status": company.subscription_status,
        "stripe_customer_id": company.stripe_customer_id,
        "trial_ends_at": company.trial_ends_at.isoformat() if company.trial_ends_at else None,
        "limits": {
            "max_projects": limits.max_projects,
            "max_participants_per_project": limits.max_participants_per_project,
            "ai_analysis": limits.ai_analysis,
            "export_csv": limits.export_csv,
            "team_members": limits.team_members,
        },
        "usage": {
            "interview_count": company.interview_count,
            "storage_bytes": company.storage_bytes,
        },
    }


@router.post("/checkout")
def create_checkout_session(
    body: CheckoutRequest,
    company: Company = Depends(get_current_company),
):
    """Create a Stripe Checkout session. Requires STRIPE_SECRET_KEY."""
    stripe_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not stripe_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing is not configured. Contact support.",
        )
    try:
        import stripe  # type: ignore
        stripe.api_key = stripe_key

        # Map tier to Stripe price ID (configure in settings)
        price_ids = {
            "team": getattr(settings, "STRIPE_PRICE_STARTER", ""),
            "lab": getattr(settings, "STRIPE_PRICE_PRO", ""),
            # Legacy aliases
            "starter": getattr(settings, "STRIPE_PRICE_STARTER", ""),
            "pro": getattr(settings, "STRIPE_PRICE_PRO", ""),
        }
        price_id = price_ids.get(body.tier)
        if not price_id:
            raise HTTPException(status_code=400, detail=f"Unknown tier: {body.tier}")

        session = stripe.checkout.Session.create(
            customer_email=company.email,
            payment_method_types=["card"],
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={"company_id": company.id},
        )
        return {"checkout_url": session.url}
    except ImportError:
        raise HTTPException(status_code=503, detail="Stripe library not installed")
    except Exception as e:
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to create checkout session")


@router.post("/portal")
def create_portal_session(
    body: PortalRequest,
    company: Company = Depends(get_current_company),
):
    """Open Stripe Customer Portal for subscription management."""
    stripe_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not stripe_key or not company.stripe_customer_id:
        raise HTTPException(status_code=503, detail="Billing portal not available")
    try:
        import stripe  # type: ignore
        stripe.api_key = stripe_key
        session = stripe.billing_portal.Session.create(
            customer=company.stripe_customer_id,
            return_url=body.return_url,
        )
        return {"portal_url": session.url}
    except Exception as e:
        logger.error("Stripe portal error: %s", e)
        raise HTTPException(status_code=500, detail="Failed to open billing portal")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """Stripe webhook handler — updates subscription status on events."""
    stripe_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    webhook_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
    if not stripe_key:
        raise HTTPException(status_code=503, detail="Billing not configured")

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        import stripe  # type: ignore
        stripe.api_key = stripe_key
        event = stripe.Webhook.construct_event(payload, sig, webhook_secret) if webhook_secret else stripe.Event.construct_from(
            stripe.util.convert_to_stripe_object(stripe.util.json.loads(payload)), stripe_key
        )
    except Exception as e:
        logger.error("Webhook error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    event_type = event["type"]
    logger.info("Stripe webhook: %s", event_type)

    if event_type in ("customer.subscription.created", "customer.subscription.updated"):
        sub = event["data"]["object"]
        company_id = sub.get("metadata", {}).get("company_id")
        if company_id:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                tier_map = {
                    getattr(settings, "STRIPE_PRICE_STARTER", ""): "team",
                    getattr(settings, "STRIPE_PRICE_PRO", ""): "lab",
                }
                price_id = sub["items"]["data"][0]["price"]["id"] if sub["items"]["data"] else ""
                company.subscription_tier = tier_map.get(price_id, company.subscription_tier)
                company.subscription_status = sub["status"]
                company.stripe_subscription_id = sub["id"]
                db.commit()
                logger.info("Updated subscription for company %s: %s / %s", company_id, company.subscription_tier, company.subscription_status)

    elif event_type == "customer.subscription.deleted":
        sub = event["data"]["object"]
        company_id = sub.get("metadata", {}).get("company_id")
        if company_id:
            company = db.query(Company).filter(Company.id == company_id).first()
            if company:
                company.subscription_tier = "solo"
                company.subscription_status = "canceled"
                db.commit()

    return {"received": True}
