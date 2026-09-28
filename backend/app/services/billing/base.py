from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session


class BillingService(ABC):
    """Abstract interface defining the billing contract for both live Stripe and mock modes."""

    @abstractmethod
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
        """Creates a checkout session for a given tier and billing interval."""
        pass

    @abstractmethod
    def create_portal_session(
        self,
        tenant_id: str,
        return_url: Optional[str] = None,
        customer_id: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Creates a customer billing portal session."""
        pass

    @abstractmethod
    def handle_webhook(
        self,
        payload: bytes | str | Dict[str, Any],
        signature: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict[str, Any]:
        """Processes an incoming webhook event idempotently."""
        pass

    @abstractmethod
    def set_tier(
        self,
        tenant_id: str,
        tier: str,
        db: Session,
        pages_used: Optional[int] = None,
        status: str = "active",
    ) -> Dict[str, Any]:
        """Directly overrides the subscription tier and updates quota usage."""
        pass
