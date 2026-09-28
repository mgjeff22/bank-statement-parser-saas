from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field, model_validator


class TierInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str
    monthly_limit: int
    price_monthly: int
    price_annual: int
    currency: str = "USD"
    stripe_price_id_monthly: Optional[str] = None
    stripe_price_id_annual: Optional[str] = None
    features: List[str] = Field(default_factory=list)


class TiersListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tiers: List[TierInfo]
    plans: List[TierInfo]


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tier: Optional[str] = None
    price_tier: Optional[str] = None
    interval: Optional[str] = "month"
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

    @model_validator(mode="after")
    def resolve_tier_and_interval(self):
        target_tier = self.tier or self.price_tier or "starter"
        target_tier = target_tier.lower()
        if target_tier not in ["free", "starter", "pro"]:
            target_tier = "starter"
        self.tier = target_tier
        self.price_tier = target_tier

        target_interval = (self.interval or "month").lower()
        if target_interval in ["annual", "year", "yearly"]:
            target_interval = "year"
        else:
            target_interval = "month"
        self.interval = target_interval
        return self


class CheckoutResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    checkout_url: str
    tier: str
    interval: str
    mode: str = "mock"


class PortalRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    return_url: Optional[str] = "http://localhost:5173/dashboard"


class PortalResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    portal_url: str


class SubscriptionQuotaInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pages_used: int
    monthly_limit: int
    pages_remaining: int
    percent_used: float
    reset_date: Optional[str] = None


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tier: str
    status: str
    monthly_page_limit: int
    billing_interval: Optional[str] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    billing_mode: str = "mock"
    quota: Optional[SubscriptionQuotaInfo] = None


class WebhookResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    action: Optional[str] = None
    received: bool = True
    event_id: Optional[str] = None
    reason: Optional[str] = None
    tier: Optional[str] = None
    detail: Optional[str] = None


class MockCompleteCheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: Optional[str] = None
    tier: Optional[str] = "starter"
    interval: Optional[str] = "month"
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None


class MockSetTierRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tier: str
    tenant_id: Optional[str] = None
    user_id: Optional[str] = None
    pages_used: Optional[int] = None
    status: Optional[str] = "active"


class MockTriggerWebhookRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: Optional[str] = None
    event_type: Optional[str] = None
    data_object: Optional[Dict[str, Any]] = None
