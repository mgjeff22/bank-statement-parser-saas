import os
from app.core.config import settings
from app.services.billing.base import BillingService
from app.services.billing.mock_service import MockBillingService
from app.services.billing.stripe_service import StripeBillingService


def get_billing_service() -> BillingService:
    """
    Returns the appropriate BillingService implementation based on the BILLING_MODE setting.
    If BILLING_MODE is 'live' and valid Stripe credentials are provided, returns StripeBillingService.
    Otherwise, defaults to the zero-config MockBillingService.
    """
    mode = os.getenv("BILLING_MODE", settings.BILLING_MODE).lower()
    stripe_key = os.getenv("STRIPE_SECRET_KEY", settings.STRIPE_SECRET_KEY or "")
    if mode == "live" and stripe_key and not stripe_key.startswith("mock"):
        return StripeBillingService()
    return MockBillingService()
