import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.models.subscription import Subscription
from app.models.quota import QuotaUsage
from app.models.billing import ProcessedStripeEvent
from app.services.billing.adapter import get_billing_service
from app.services.billing.mock_service import MockBillingService
from app.services.billing.stripe_service import StripeBillingService

engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(autouse=True)
def setup_test_database():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_user(client: TestClient, email: str = "billing_user@example.com") -> dict:
    res = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "organization_name": "Billing Test Org",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------- Tiers & Plans Tests ----------------

def test_list_tiers_and_plans(client):
    """Verifies that available tiers list Free (5 pgs), Starter (50 pgs), and Pro (500 pgs)."""
    res = client.get("/api/billing/tiers")
    assert res.status_code == 200
    data = res.json()
    assert "tiers" in data
    tiers = {t["id"]: t for t in data["tiers"]}

    assert "free" in tiers
    assert tiers["free"]["monthly_limit"] == 5
    assert tiers["free"]["price_monthly"] == 0

    assert "starter" in tiers
    assert tiers["starter"]["monthly_limit"] == 50
    assert tiers["starter"]["price_monthly"] == 19
    assert tiers["starter"]["price_annual"] == 190

    assert "pro" in tiers
    assert tiers["pro"]["monthly_limit"] == 500
    assert tiers["pro"]["price_monthly"] == 49
    assert tiers["pro"]["price_annual"] == 490

    # Also test /plans alias
    res_plans = client.get("/api/billing/plans")
    assert res_plans.status_code == 200
    assert "plans" in res_plans.json()


# ---------------- Checkout Session Tests ----------------

def test_checkout_session_starter_monthly(client):
    """Verifies creation of a Starter monthly checkout session."""
    user = register_user(client, "starter_monthly@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/checkout",
        json={"tier": "starter", "interval": "month"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert "checkout_url" in data
    assert data["tier"] == "starter"
    assert data["interval"] == "month"
    assert data["checkout_url"].startswith("https://checkout.stripe.com/")


def test_checkout_session_starter_annual(client):
    """Verifies creation of a Starter annual checkout session."""
    user = register_user(client, "starter_annual@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/checkout",
        json={"price_tier": "starter", "interval": "year"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "starter"
    assert data["interval"] == "year"


def test_checkout_session_pro_monthly(client):
    """Verifies creation of a Pro monthly checkout session."""
    user = register_user(client, "pro_monthly@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/checkout",
        json={"tier": "pro", "interval": "month"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "pro"
    assert data["interval"] == "month"


def test_checkout_session_pro_annual(client):
    """Verifies creation of a Pro annual checkout session."""
    user = register_user(client, "pro_annual@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/create-checkout-session",
        json={"price_tier": "pro", "interval": "annual"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "pro"
    assert data["interval"] == "year"


def test_checkout_session_unauthenticated(client):
    """Verifies unauthenticated checkout session succeeds using mock fallback."""
    res = client.post(
        "/api/billing/checkout",
        json={"tier": "starter"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert "checkout_url" in data


# ---------------- Customer Portal Tests ----------------

def test_portal_session_authenticated(client):
    """Verifies customer billing portal session generation for authenticated user."""
    user = register_user(client, "portal_auth@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/portal",
        json={"return_url": "http://localhost:5173/dashboard"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert "portal_url" in data
    assert data["portal_url"].startswith("https://billing.stripe.com/")


def test_portal_session_unauthenticated(client):
    """Verifies unauthenticated customer portal request gracefully returns portal URL."""
    res = client.post(
        "/api/billing/create-portal-session",
        json={},
    )
    assert res.status_code == 200
    data = res.json()
    assert "portal_url" in data


# ---------------- Subscription Status Tests ----------------

def test_get_subscription_status(client):
    """Verifies subscription status retrieval for default free account."""
    user = register_user(client, "sub_status@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.get("/api/billing/subscription", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["tier"] == "free"
    assert data["status"] == "active"
    assert data["monthly_page_limit"] == 5
    assert data["quota"]["monthly_limit"] == 5
    assert data["quota"]["pages_used"] == 0
    assert data["quota"]["pages_remaining"] == 5


# ---------------- Mock Control Endpoints Tests ----------------

def test_mock_complete_checkout_upgrades_tier(client):
    """Verifies that POST /api/billing/mock/complete-checkout activates subscription immediately."""
    user = register_user(client, "complete_checkout@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/mock/complete-checkout",
        json={"tier": "starter", "interval": "month"},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "processed"
    assert data["action"] == "subscription_activated"

    # Verify subscription is now Starter with 50 pages limit
    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.status_code == 200
    sub_data = sub_res.json()
    assert sub_data["tier"] == "starter"
    assert sub_data["monthly_page_limit"] == 50
    assert sub_data["quota"]["monthly_limit"] == 50


def test_mock_complete_checkout_pro(client):
    """Verifies immediate checkout completion to Pro tier."""
    user = register_user(client, "pro_checkout@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/mock/complete-checkout",
        json={"tier": "pro", "interval": "year"},
        headers=headers,
    )
    assert res.status_code == 200

    sub_res = client.get("/api/billing/subscription", headers=headers)
    sub_data = sub_res.json()
    assert sub_data["tier"] == "pro"
    assert sub_data["monthly_page_limit"] == 500


def test_mock_set_tier_direct(client):
    """Verifies that POST /api/billing/mock/set-tier directly alters tier and quota limits."""
    user = register_user(client, "direct_tier@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/mock/set-tier",
        json={"tier": "pro", "pages_used": 15},
        headers=headers,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["tier"] == "pro"
    assert data["monthly_limit"] == 500
    assert data["pages_used"] == 15

    # Check via subscription endpoint
    sub_res = client.get("/api/billing/subscription", headers=headers)
    sub_data = sub_res.json()
    assert sub_data["tier"] == "pro"
    assert sub_data["quota"]["pages_used"] == 15
    assert sub_data["quota"]["pages_remaining"] == 485


def test_mock_reset_quota(client):
    """Verifies that POST /api/billing/mock/reset-quota resets page usage to 0."""
    user = register_user(client, "reset_quota@example.com")
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    # Set usage first
    client.post(
        "/api/billing/mock/set-tier",
        json={"tier": "starter", "pages_used": 35},
        headers=headers,
    )

    res = client.post("/api/billing/mock/reset-quota", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["pages_used"] == 0

    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.json()["quota"]["pages_used"] == 0


# ---------------- Adapter Tests ----------------

def test_adapter_mode_toggle(monkeypatch):
    """Verifies that get_billing_service() selects the correct service according to BILLING_MODE."""
    # Default is mock
    service = get_billing_service()
    assert isinstance(service, MockBillingService)

    # When live and with valid key
    monkeypatch.setenv("BILLING_MODE", "live")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_valid_key_1234567890")
    service_live = get_billing_service()
    assert isinstance(service_live, StripeBillingService)

    # When live but key is mock_secret
    monkeypatch.setenv("STRIPE_SECRET_KEY", "mock_secret")
    service_fallback = get_billing_service()
    assert isinstance(service_fallback, MockBillingService)
