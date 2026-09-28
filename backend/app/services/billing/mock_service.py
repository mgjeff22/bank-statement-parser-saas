import json
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.subscription import Subscription
from app.models.quota import QuotaUsage
from app.models.user import User
from app.models.tenant import Tenant
from app.models.billing import ProcessedStripeEvent
from app.services.quota import get_or_create_quota, TIER_LIMITS
from app.services.billing.base import BillingService


class MockBillingService(BillingService):
    """
    Zero-config local Mock billing adapter supporting simulated checkout completion,
    simulated portal redirect URL, synthetic webhook simulation, and direct tier setting.
    Operates with zero external network calls.
    """

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
        if tier not in ["free", "starter", "pro"]:
            tier = "starter"

        interval = (interval or "month").lower()
        if interval in ["annual", "year", "yearly"]:
            interval = "year"
        else:
            interval = "month"

        session_id = f"cs_test_{tier}_{interval}_{uuid.uuid4().hex[:8]}"
        checkout_url = f"https://checkout.stripe.com/c/pay/{session_id}"

        return {
            "session_id": session_id,
            "checkout_url": checkout_url,
            "tier": tier,
            "interval": interval,
            "mode": "mock",
            "success_url": success_url,
            "cancel_url": cancel_url,
        }

    def create_portal_session(
        self,
        tenant_id: str,
        return_url: Optional[str] = None,
        customer_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        return_url = return_url or "http://localhost:5173/dashboard"
        session_id = f"test_portal_session_{uuid.uuid4().hex[:8]}"
        portal_url = f"https://billing.stripe.com/p/session/{session_id}"
        return {
            "portal_url": portal_url,
            "session_id": session_id,
            "return_url": return_url,
        }

    def set_tier(
        self,
        tenant_id: str,
        tier: str,
        db: Session,
        pages_used: Optional[int] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        tier = (tier or "free").lower()
        if tier not in TIER_LIMITS:
            tier = "free"
        limit = TIER_LIMITS.get(tier, settings.FREE_PAGE_LIMIT)

        sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
        if not sub:
            sub = Subscription(
                id=f"sub_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                tier=tier,
                status=status,
                monthly_page_limit=limit,
                current_period_start=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(sub)
        else:
            sub.tier = tier
            sub.status = status
            sub.monthly_page_limit = limit
            sub.updated_at = datetime.now(timezone.utc)

        quota = get_or_create_quota(tenant_id, db)
        quota.monthly_limit = limit
        if pages_used is not None:
            quota.pages_used = max(0, pages_used)
        quota.updated_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(sub)
        db.refresh(quota)

        return {
            "success": True,
            "tenant_id": tenant_id,
            "tier": sub.tier,
            "monthly_limit": quota.monthly_limit,
            "pages_used": quota.pages_used,
            "status": sub.status,
        }

    def handle_webhook(
        self,
        payload: bytes | str | Dict[str, Any],
        signature: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Processes mock webhook with deduplication and state machine."""
        close_db_when_done = False
        if db is None:
            db = SessionLocal()
            close_db_when_done = True

        try:
            return self._process_webhook_event(payload, db)
        finally:
            if close_db_when_done:
                db.close()

    def _process_webhook_event(
        self,
        payload: bytes | str | Dict[str, Any],
        db: Session,
    ) -> Dict[str, Any]:
        raw_bytes = b""
        if isinstance(payload, bytes):
            raw_bytes = payload
            try:
                event = json.loads(payload.decode("utf-8"))
            except Exception:
                event = {}
        elif isinstance(payload, str):
            raw_bytes = payload.encode("utf-8")
            try:
                event = json.loads(payload)
            except Exception:
                event = {}
        elif isinstance(payload, dict):
            event = payload
            raw_bytes = json.dumps(payload).encode("utf-8")
        else:
            event = {}

        event_id = event.get("id") or event.get("event_id") or f"evt_mock_{uuid.uuid4().hex[:10]}"
        event_type = event.get("type") or event.get("event_type") or "unknown"
        data_object = event.get("data", {}).get("object", {}) if "data" in event else (event.get("data_object") or event)

        payload_hash = hashlib.sha256(raw_bytes).hexdigest() if raw_bytes else None

        # Idempotency / Deduplication check in ProcessedStripeEvent table
        existing = db.query(ProcessedStripeEvent).filter(ProcessedStripeEvent.event_id == event_id).first()
        if existing:
            return {
                "status": "ignored",
                "reason": "duplicate_event_id",
                "received": True,
                "event_id": event_id,
            }

        processed_record = ProcessedStripeEvent(
            id=f"pse_{uuid.uuid4().hex[:12]}",
            event_id=event_id,
            event_type=event_type,
            processed_at=datetime.now(timezone.utc),
            payload_hash=payload_hash,
            status="processed",
        )
        try:
            db.add(processed_record)
            db.commit()
        except IntegrityError:
            db.rollback()
            return {
                "status": "ignored",
                "reason": "duplicate_event_id",
                "received": True,
                "event_id": event_id,
            }

        # Resolve target tenant
        tenant_id = self._resolve_target_tenant(data_object, db)

        # Lifecycle State Machine
        if event_type == "checkout.session.completed":
            tier = (
                data_object.get("metadata", {}).get("tier")
                or data_object.get("tier")
                or "starter"
            ).lower()
            if tier not in TIER_LIMITS:
                tier = "starter"
            limit = TIER_LIMITS.get(tier, 50)
            customer_id = data_object.get("customer") or f"cus_{uuid.uuid4().hex[:10]}"
            sub_id = data_object.get("subscription") or f"sub_stripe_{uuid.uuid4().hex[:10]}"

            if tenant_id:
                sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
                if not sub:
                    sub = Subscription(
                        id=f"sub_{uuid.uuid4().hex[:12]}",
                        tenant_id=tenant_id,
                        tier=tier,
                        status="active",
                        monthly_page_limit=limit,
                        stripe_customer_id=customer_id,
                        stripe_subscription_id=sub_id,
                        current_period_start=datetime.now(timezone.utc),
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    db.add(sub)
                else:
                    sub.tier = tier
                    sub.status = "active"
                    sub.stripe_customer_id = customer_id
                    sub.stripe_subscription_id = sub_id
                    sub.monthly_page_limit = limit
                    sub.updated_at = datetime.now(timezone.utc)

                quota = get_or_create_quota(tenant_id, db)
                quota.monthly_limit = limit
                db.commit()

            return {
                "status": "processed",
                "action": "subscription_activated",
                "tier": tier,
                "received": True,
                "event_id": event_id,
            }

        elif event_type == "customer.subscription.updated":
            tier = (
                data_object.get("metadata", {}).get("tier")
                or data_object.get("tier")
            )
            sub_status = data_object.get("status", "active")
            cancel_at_period_end = data_object.get("cancel_at_period_end", False)

            if tenant_id:
                sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
                if sub:
                    if tier:
                        tier = tier.lower()
                        if tier in TIER_LIMITS:
                            sub.tier = tier
                            sub.monthly_page_limit = TIER_LIMITS[tier]
                            quota = get_or_create_quota(tenant_id, db)
                            quota.monthly_limit = TIER_LIMITS[tier]
                    sub.status = sub_status
                    sub.cancel_at_period_end = bool(cancel_at_period_end)
                    sub.updated_at = datetime.now(timezone.utc)
                    db.commit()

            return {
                "status": "processed",
                "action": "subscription_updated",
                "tier": tier,
                "received": True,
                "event_id": event_id,
            }

        elif event_type == "customer.subscription.deleted":
            if tenant_id:
                sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
                if sub:
                    sub.tier = "free"
                    sub.status = "canceled"
                    sub.monthly_page_limit = settings.FREE_PAGE_LIMIT
                    sub.stripe_subscription_id = None
                    sub.cancel_at_period_end = False
                    sub.updated_at = datetime.now(timezone.utc)

                quota = get_or_create_quota(tenant_id, db)
                quota.monthly_limit = settings.FREE_PAGE_LIMIT
                db.commit()

            return {
                "status": "processed",
                "action": "subscription_cancelled",
                "tier": "free",
                "received": True,
                "event_id": event_id,
            }

        elif event_type == "invoice.payment_succeeded":
            if tenant_id:
                quota = get_or_create_quota(tenant_id, db)
                quota.pages_used = 0
                quota.last_reset_at = datetime.now(timezone.utc)
                quota.updated_at = datetime.now(timezone.utc)

                sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
                if sub:
                    sub.status = "active"
                    sub.updated_at = datetime.now(timezone.utc)
                db.commit()

            return {
                "status": "processed",
                "action": "quota_reset_success",
                "received": True,
                "event_id": event_id,
            }

        elif event_type == "invoice.payment_failed":
            if tenant_id:
                sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
                if sub:
                    sub.status = "past_due"
                    sub.updated_at = datetime.now(timezone.utc)
                    db.commit()

            return {
                "status": "processed",
                "action": "payment_failed_recorded",
                "received": True,
                "event_id": event_id,
            }

        return {
            "status": "processed",
            "action": "unhandled_event",
            "received": True,
            "event_id": event_id,
        }

    def _resolve_target_tenant(self, data_object: Dict[str, Any], db: Session) -> Optional[str]:
        """Resolves target tenant_id from various metadata and relationship cues."""
        if not data_object or not isinstance(data_object, dict):
            first_tenant = db.query(Tenant).first()
            return first_tenant.id if first_tenant else None

        # 1. Direct tenant_id in data_object or metadata
        metadata = data_object.get("metadata") or {}
        if isinstance(metadata, dict) and metadata.get("tenant_id"):
            return metadata["tenant_id"]
        if data_object.get("tenant_id"):
            return data_object["tenant_id"]

        # 2. client_reference_id
        if data_object.get("client_reference_id"):
            ref_id = data_object["client_reference_id"]
            if db.query(Tenant).filter(Tenant.id == ref_id).first():
                return ref_id
            user = db.query(User).filter(User.id == ref_id).first()
            if user:
                return user.tenant_id

        # 3. user_id
        user_id = metadata.get("user_id") if isinstance(metadata, dict) else None
        if not user_id:
            user_id = data_object.get("user_id")
        if user_id:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user.tenant_id

        # 4. stripe_customer_id
        cust_id = data_object.get("customer")
        if cust_id:
            sub = db.query(Subscription).filter(Subscription.stripe_customer_id == cust_id).first()
            if sub:
                return sub.tenant_id

        # 5. stripe_subscription_id
        sub_id = data_object.get("subscription") or data_object.get("id")
        if sub_id:
            sub = db.query(Subscription).filter(Subscription.stripe_subscription_id == sub_id).first()
            if sub:
                return sub.tenant_id

        # 6. Fallback: return first tenant if available
        first_tenant = db.query(Tenant).order_by(Tenant.created_at.desc()).first()
        return first_tenant.id if first_tenant else None
