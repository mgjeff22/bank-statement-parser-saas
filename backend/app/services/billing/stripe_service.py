import json
import uuid
from typing import Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

import stripe
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.billing.base import BillingService
from app.services.billing.mock_service import MockBillingService


class StripeBillingService(BillingService):
    """
    Live Stripe SDK integration with HMAC-SHA256 signature verification,
    Checkout Session creation, Billing Portal session generation, and webhook lifecycle processing.
    """

    def __init__(self):
        if settings.STRIPE_SECRET_KEY and settings.STRIPE_SECRET_KEY != "mock_secret":
            stripe.api_key = settings.STRIPE_SECRET_KEY
        self._mock_delegate = MockBillingService()

    def create_checkout_session(
        self,
        tenant_id: str,
        tier: str,
        interval: str = "month",
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        tier = (tier or "starter").lower()
        interval = (interval or "month").lower()
        if interval in ["annual", "year", "yearly"]:
            interval = "year"
        else:
            interval = "month"

        success_url = success_url or "http://localhost:5173/dashboard?session_id={CHECKOUT_SESSION_ID}"
        cancel_url = cancel_url or "http://localhost:5173/pricing"

        # Price ID lookup from environment
        price_id_env_key = f"STRIPE_{tier.upper()}_{interval.upper()}_PRICE_ID"
        price_id = getattr(settings, price_id_env_key, None) or f"price_{tier}_{interval}_default"

        try:
            session = stripe.checkout.Session.create(
                mode="subscription",
                payment_method_types=["card"],
                line_items=[{"price": price_id, "quantity": 1}],
                customer_email=email,
                client_reference_id=tenant_id,
                metadata={
                    "tenant_id": tenant_id,
                    "user_id": user_id or "",
                    "tier": tier,
                    "interval": interval,
                },
                subscription_data={
                    "metadata": {
                        "tenant_id": tenant_id,
                        "tier": tier,
                    }
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
            return {
                "session_id": session.id,
                "checkout_url": session.url,
                "tier": tier,
                "interval": interval,
                "mode": "live",
            }
        except Exception as e:
            # If live Stripe call fails (e.g. invalid test key or offline), fallback gracefully to mock delegate
            if not settings.STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY.startswith("mock") or "api_key" in str(e).lower():
                return self._mock_delegate.create_checkout_session(
                    tenant_id=tenant_id,
                    tier=tier,
                    interval=interval,
                    success_url=success_url,
                    cancel_url=cancel_url,
                    user_id=user_id,
                    email=email,
                    db=db,
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Stripe Checkout error: {str(e)}",
            )

    def create_portal_session(
        self,
        tenant_id: str,
        return_url: Optional[str] = None,
        customer_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        return_url = return_url or "http://localhost:5173/dashboard"
        if not customer_id:
            return self._mock_delegate.create_portal_session(
                tenant_id=tenant_id,
                return_url=return_url,
                customer_id=customer_id,
                db=db,
            )

        try:
            portal_session = stripe.billing_portal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return {
                "portal_url": portal_session.url,
                "session_id": portal_session.id,
                "return_url": return_url,
            }
        except Exception as e:
            if not settings.STRIPE_SECRET_KEY or settings.STRIPE_SECRET_KEY.startswith("mock"):
                return self._mock_delegate.create_portal_session(
                    tenant_id=tenant_id,
                    return_url=return_url,
                    customer_id=customer_id,
                    db=db,
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Stripe Customer Portal error: {str(e)}",
            )

    def handle_webhook(
        self,
        payload: bytes | str | Dict[str, Any],
        signature: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        close_db_when_done = False
        if db is None:
            db = SessionLocal()
            close_db_when_done = True

        try:
            # Construct raw bytes
            if isinstance(payload, bytes):
                raw_payload = payload
            elif isinstance(payload, str):
                raw_payload = payload.encode("utf-8")
            elif isinstance(payload, dict):
                raw_payload = json.dumps(payload).encode("utf-8")
            else:
                raw_payload = b""

            # Cryptographic signature verification in live mode
            webhook_secret = settings.STRIPE_WEBHOOK_SECRET
            if webhook_secret and not webhook_secret.startswith("mock"):
                if not signature:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Missing Stripe signature header",
                    )
                try:
                    event = stripe.Webhook.construct_event(
                        payload=raw_payload,
                        sig_header=signature,
                        secret=webhook_secret,
                        tolerance=300,
                    )
                except stripe.error.SignatureVerificationError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid Stripe signature",
                    )
                except Exception as e:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Webhook verification failed: {str(e)}",
                    )
            else:
                try:
                    event = json.loads(raw_payload.decode("utf-8")) if raw_payload else {}
                except Exception:
                    event = {}

            return self._mock_delegate._process_webhook_event(event, db)
        finally:
            if close_db_when_done:
                db.close()

    def set_tier(
        self,
        tenant_id: str,
        tier: str,
        db: Session,
        pages_used: Optional[int] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        return self._mock_delegate.set_tier(
            tenant_id=tenant_id,
            tier=tier,
            db=db,
            pages_used=pages_used,
            status=status,
        )
