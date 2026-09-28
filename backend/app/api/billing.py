import json
import uuid
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, Header, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_optional, get_current_user
from app.models.tenant import Tenant
from app.models.user import User
from app.models.subscription import Subscription
from app.models.quota import QuotaUsage
from app.services.quota import get_or_create_quota, TIER_LIMITS
from app.services.billing.adapter import get_billing_service
from app.schemas.billing import (
    TierInfo,
    TiersListResponse,
    CheckoutRequest,
    CheckoutResponse,
    PortalRequest,
    PortalResponse,
    SubscriptionResponse,
    SubscriptionQuotaInfo,
    WebhookResponse,
    MockCompleteCheckoutRequest,
    MockSetTierRequest,
    MockTriggerWebhookRequest,
)

router = APIRouter()

AVAILABLE_TIERS: List[TierInfo] = [
    TierInfo(
        id="free",
        name="Free Tier",
        description="Essential bank statement extraction for personal finances.",
        monthly_limit=5,
        price_monthly=0,
        price_annual=0,
        currency="USD",
        features=[
            "5 pages / month",
            "Digital & scanned statement parsing",
            "Mathematical balance reconciliation",
            "CSV & JSON export",
            "7-day history retention",
        ],
    ),
    TierInfo(
        id="starter",
        name="Starter",
        description="Perfect for freelancers, bookkeepers, and regular statement auditing.",
        monthly_limit=50,
        price_monthly=19,
        price_annual=190,
        currency="USD",
        stripe_price_id_monthly="price_starter_monthly",
        stripe_price_id_annual="price_starter_annual",
        features=[
            "50 pages / month",
            "Standard OCR priority",
            "Formatted Excel (.xlsx) export with formulas",
            "90-day history retention",
            "Up to 3 concurrent uploads",
        ],
    ),
    TierInfo(
        id="pro",
        name="Pro",
        description="High-volume parsing engine for accounting practices and SMBs.",
        monthly_limit=500,
        price_monthly=49,
        price_annual=490,
        currency="USD",
        stripe_price_id_monthly="price_pro_monthly",
        stripe_price_id_annual="price_pro_annual",
        features=[
            "500 pages / month",
            "Priority parallel OCR queue",
            "Bulk statement processing",
            "Unlimited history retention",
            "Up to 10 concurrent uploads",
            "Priority email support",
        ],
    ),
]


def _resolve_tenant_id(
    current_user: Optional[User],
    explicit_tenant_id: Optional[str],
    db: Session,
) -> str:
    """Helper to resolve a tenant_id from user, parameter, or DB fallback."""
    if current_user and current_user.tenant_id:
        return current_user.tenant_id
    if explicit_tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == explicit_tenant_id).first()
        if tenant:
            return tenant.id

    first_tenant = db.query(Tenant).order_by(Tenant.created_at.desc()).first()
    if first_tenant:
        return first_tenant.id

    # Create fallback tenant
    new_id = f"ten_mock_{uuid.uuid4().hex[:8]}"
    new_tenant = Tenant(id=new_id, name="Default Mock Tenant")
    db.add(new_tenant)
    db.commit()
    return new_id


@router.get("/tiers", response_model=TiersListResponse)
@router.get("/plans", response_model=TiersListResponse)
def list_tiers():
    """Returns all available subscription tiers with prices, page limits, and feature lists."""
    return TiersListResponse(tiers=AVAILABLE_TIERS, plans=AVAILABLE_TIERS)


@router.get("/subscription", response_model=SubscriptionResponse)
def get_subscription(
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Retrieves current user's subscription status, billing interval, and page quota metrics."""
    tenant_id = _resolve_tenant_id(current_user, None, db)

    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    tier = sub.tier if sub else "free"
    sub_status = sub.status if sub else "active"
    monthly_limit = sub.monthly_page_limit if sub else settings.FREE_PAGE_LIMIT

    quota = get_or_create_quota(tenant_id, db)
    pages_used = quota.pages_used
    pages_remaining = max(0, quota.monthly_limit - pages_used)
    percent_used = round((pages_used / quota.monthly_limit * 100.0), 2) if quota.monthly_limit > 0 else 0.0

    return SubscriptionResponse(
        tier=tier,
        status=sub_status,
        monthly_page_limit=monthly_limit,
        billing_interval="month",
        current_period_start=sub.current_period_start if sub else None,
        current_period_end=sub.current_period_end if sub else None,
        cancel_at_period_end=sub.cancel_at_period_end if sub else False,
        billing_mode=settings.BILLING_MODE,
        quota=SubscriptionQuotaInfo(
            pages_used=pages_used,
            monthly_limit=quota.monthly_limit,
            pages_remaining=pages_remaining,
            percent_used=percent_used,
            reset_date=quota.last_reset_at.isoformat() if quota.last_reset_at else None,
        ),
    )


@router.post("/checkout", response_model=CheckoutResponse)
@router.post("/create-checkout-session", response_model=CheckoutResponse)
def create_checkout(
    req: CheckoutRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Creates a Stripe Checkout Session or Mock Checkout Session for the selected tier."""
    tenant_id = _resolve_tenant_id(current_user, None, db)
    billing_service = get_billing_service()

    session_data = billing_service.create_checkout_session(
        tenant_id=tenant_id,
        tier=req.tier or "starter",
        interval=req.interval or "month",
        success_url=req.success_url,
        cancel_url=req.cancel_url,
        user_id=current_user.id if current_user else None,
        email=current_user.email if current_user else None,
        db=db,
    )
    return CheckoutResponse(**session_data)


@router.post("/portal", response_model=PortalResponse)
@router.post("/create-portal-session", response_model=PortalResponse)
def create_portal(
    req: Optional[PortalRequest] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Generates a Stripe Customer Portal session or Mock Portal URL."""
    tenant_id = _resolve_tenant_id(current_user, None, db)
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    customer_id = sub.stripe_customer_id if sub else None

    return_url = req.return_url if req else "http://localhost:5173/dashboard"
    billing_service = get_billing_service()

    portal_data = billing_service.create_portal_session(
        tenant_id=tenant_id,
        return_url=return_url,
        customer_id=customer_id,
        db=db,
    )
    return PortalResponse(**portal_data)


@router.post("/webhook", response_model=WebhookResponse)
async def handle_stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
    db: Session = Depends(get_db),
):
    """
    Idempotent Stripe webhook receiver verifying signature (if live)
    and checking ProcessedStripeEvent deduplication table.
    """
    raw_payload = await request.body()
    billing_service = get_billing_service()

    result = billing_service.handle_webhook(
        payload=raw_payload,
        signature=stripe_signature,
        db=db,
    )
    return WebhookResponse(**result)


# ---------------- Mock Test Control Endpoints ----------------

@router.post("/mock/complete-checkout", response_model=WebhookResponse)
def mock_complete_checkout(
    req: MockCompleteCheckoutRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Mock endpoint to immediately complete checkout and upgrade tier."""
    target_tenant_id = _resolve_tenant_id(current_user, req.tenant_id, db)
    tier = (req.tier or "starter").lower()
    interval = (req.interval or "month").lower()
    session_id = req.session_id or f"cs_test_{tier}_{uuid.uuid4().hex[:8]}"

    synthetic_event = {
        "id": f"evt_checkout_{uuid.uuid4().hex[:10]}",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": session_id,
                "customer": f"cus_mock_{uuid.uuid4().hex[:8]}",
                "subscription": f"sub_mock_{uuid.uuid4().hex[:8]}",
                "metadata": {
                    "tenant_id": target_tenant_id,
                    "user_id": req.user_id or (current_user.id if current_user else ""),
                    "tier": tier,
                    "interval": interval,
                },
                "tier": tier,
            }
        },
    }

    billing_service = get_billing_service()
    result = billing_service.handle_webhook(payload=synthetic_event, db=db)
    return WebhookResponse(**result)


@router.post("/mock/trigger-webhook", response_model=WebhookResponse)
async def mock_trigger_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """Mock endpoint to trigger synthetic webhooks without live Stripe signatures."""
    try:
        body = await request.json()
    except Exception:
        body = {}

    billing_service = get_billing_service()
    result = billing_service.handle_webhook(payload=body, db=db)
    return WebhookResponse(**result)


@router.post("/mock/set-tier")
def mock_set_tier(
    req: MockSetTierRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Direct tier setter for automated testing."""
    target_tenant_id = _resolve_tenant_id(current_user, req.tenant_id, db)
    billing_service = get_billing_service()

    result = billing_service.set_tier(
        tenant_id=target_tenant_id,
        tier=req.tier,
        db=db,
        pages_used=req.pages_used,
        status=req.status or "active",
    )
    return result


@router.post("/mock/reset-quota")
def mock_reset_quota(
    tenant_id: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Resets quota usage for the tenant to 0."""
    target_tenant_id = _resolve_tenant_id(current_user, tenant_id, db)
    quota = get_or_create_quota(target_tenant_id, db)
    quota.pages_used = 0
    db.commit()
    db.refresh(quota)
    return {"success": True, "tenant_id": target_tenant_id, "pages_used": 0, "monthly_limit": quota.monthly_limit}
