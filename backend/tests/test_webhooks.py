import json
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
from app.core.config import settings

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


def register_user(client: TestClient, email: str = "webhook_user@example.com") -> dict:
    res = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "SecurePassword123!",
            "organization_name": "Webhook Test Org",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()


# ---------------- Idempotency Tests ----------------

def test_webhook_first_delivery_processed(client):
    """Verifies that an incoming webhook event is processed successfully on first delivery."""
    event_payload = {
        "id": "evt_test_001",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "tier": "starter",
                "customer": "cus_123",
            }
        },
    }
    res = client.post(
        "/api/billing/webhook",
        content=json.dumps(event_payload),
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "processed"
    assert data["action"] == "subscription_activated"
    assert data["received"] is True
    assert data["event_id"] == "evt_test_001"


def test_webhook_duplicate_delivery_ignored(client):
    """Verifies that a duplicate delivery of an identical event_id is safely ignored."""
    event_payload = {
        "id": "evt_duplicate_check",
        "type": "checkout.session.completed",
        "data": {"object": {"tier": "starter"}},
    }
    # First delivery
    res1 = client.post("/api/billing/webhook", content=json.dumps(event_payload))
    assert res1.status_code == 200
    assert res1.json()["status"] == "processed"

    # Second delivery
    res2 = client.post("/api/billing/webhook", content=json.dumps(event_payload))
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["status"] == "ignored"
    assert data2["reason"] == "duplicate_event_id"
    assert data2["event_id"] == "evt_duplicate_check"


def test_webhook_five_replays_single_execution(client):
    """Verifies delivering the exact same event 5 times only executes once and ignores 4 times."""
    event_payload = {
        "id": "evt_five_replays",
        "type": "invoice.payment_succeeded",
        "data": {"object": {}},
    }
    results = [
        client.post("/api/billing/webhook", content=json.dumps(event_payload)).json()
        for _ in range(5)
    ]
    processed = [r for r in results if r["status"] == "processed"]
    ignored = [r for r in results if r["status"] == "ignored"]

    assert len(processed) == 1
    assert len(ignored) == 4
    assert all(r["reason"] == "duplicate_event_id" for r in ignored)


def test_webhook_deduplication_table_persistence(client, db_session):
    """Verifies that processed event IDs are persisted in the ProcessedStripeEvent database table."""
    event_payload = {
        "id": "evt_table_persist",
        "type": "customer.subscription.updated",
        "data": {"object": {"status": "active"}},
    }
    client.post("/api/billing/webhook", content=json.dumps(event_payload))

    record = db_session.query(ProcessedStripeEvent).filter(
        ProcessedStripeEvent.event_id == "evt_table_persist"
    ).first()
    assert record is not None
    assert record.event_id == "evt_table_persist"
    assert record.event_type == "customer.subscription.updated"
    assert record.status == "processed"
    assert record.payload_hash is not None


# ---------------- Lifecycle State Machine Tests ----------------

def test_webhook_checkout_session_completed_upgrades_tier(client):
    """Verifies checkout.session.completed updates subscription tier and monthly page limit."""
    user = register_user(client, "checkout_hook@example.com")
    tenant_id = user["tenant_id"]

    event_payload = {
        "id": "evt_checkout_upgrade",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant_id, "tier": "starter"},
                "customer": "cus_stripe_111",
                "subscription": "sub_stripe_111",
                "tier": "starter",
            }
        },
    }
    res = client.post("/api/billing/webhook", content=json.dumps(event_payload))
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert res.json()["action"] == "subscription_activated"

    headers = {"Authorization": f"Bearer {user['access_token']}"}
    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.json()["tier"] == "starter"
    assert sub_res.json()["monthly_page_limit"] == 50
    assert sub_res.json()["quota"]["monthly_limit"] == 50


def test_webhook_customer_subscription_updated_plan_switch(client):
    """Verifies customer.subscription.updated mid-cycle upgrade elevates quota immediately."""
    user = register_user(client, "sub_update_user@example.com")
    tenant_id = user["tenant_id"]
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    # Start as starter
    client.post("/api/billing/mock/set-tier", json={"tier": "starter", "pages_used": 20}, headers=headers)

    # Deliver subscription updated to pro
    event_payload = {
        "id": "evt_sub_upgrade_pro",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant_id, "tier": "pro"},
                "status": "active",
                "cancel_at_period_end": False,
            }
        },
    }
    res = client.post("/api/billing/webhook", content=json.dumps(event_payload))
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert res.json()["action"] == "subscription_updated"

    # Verify limit is 500 and usage 20 was preserved
    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.json()["tier"] == "pro"
    assert sub_res.json()["monthly_page_limit"] == 500
    assert sub_res.json()["quota"]["pages_used"] == 20
    assert sub_res.json()["quota"]["pages_remaining"] == 480


def test_webhook_customer_subscription_updated_past_due(client):
    """Verifies customer.subscription.updated marks status as past_due."""
    user = register_user(client, "sub_past_due@example.com")
    tenant_id = user["tenant_id"]
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    client.post("/api/billing/mock/set-tier", json={"tier": "starter"}, headers=headers)

    event_payload = {
        "id": "evt_sub_past_due",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant_id},
                "status": "past_due",
            }
        },
    }
    client.post("/api/billing/webhook", content=json.dumps(event_payload))

    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.json()["status"] == "past_due"


def test_webhook_customer_subscription_deleted_downgrades_to_free(client):
    """Verifies customer.subscription.deleted downgrades account immediately to Free (5 pages)."""
    user = register_user(client, "deleted_sub_user@example.com")
    tenant_id = user["tenant_id"]
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    # Start on Pro
    client.post("/api/billing/mock/set-tier", json={"tier": "pro"}, headers=headers)

    event_payload = {
        "id": "evt_sub_deleted",
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant_id},
                "status": "canceled",
            }
        },
    }
    res = client.post("/api/billing/webhook", content=json.dumps(event_payload))
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert res.json()["action"] == "subscription_cancelled"

    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.json()["tier"] == "free"
    assert sub_res.json()["monthly_page_limit"] == 5
    assert sub_res.json()["quota"]["monthly_limit"] == 5


def test_webhook_invoice_payment_succeeded_resets_quota(client):
    """Verifies invoice.payment_succeeded resets pages_used to 0 upon cycle renewal."""
    user = register_user(client, "renewal_hook_user@example.com")
    tenant_id = user["tenant_id"]
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    # Set usage to 45 pages
    client.post("/api/billing/mock/set-tier", json={"tier": "starter", "pages_used": 45}, headers=headers)

    event_payload = {
        "id": "evt_invoice_paid",
        "type": "invoice.payment_succeeded",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant_id},
                "billing_reason": "subscription_cycle",
            }
        },
    }
    res = client.post("/api/billing/webhook", content=json.dumps(event_payload))
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert res.json()["action"] == "quota_reset_success"

    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.json()["quota"]["pages_used"] == 0
    assert sub_res.json()["quota"]["pages_remaining"] == 50


def test_webhook_invoice_payment_failed_records_past_due(client):
    """Verifies invoice.payment_failed marks the subscription status as past_due."""
    user = register_user(client, "invoice_failed_user@example.com")
    tenant_id = user["tenant_id"]
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    event_payload = {
        "id": "evt_invoice_failed",
        "type": "invoice.payment_failed",
        "data": {
            "object": {
                "metadata": {"tenant_id": tenant_id},
            }
        },
    }
    res = client.post("/api/billing/webhook", content=json.dumps(event_payload))
    assert res.status_code == 200
    assert res.json()["action"] == "payment_failed_recorded"

    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.json()["status"] == "past_due"


def test_webhook_unhandled_event_gracefully_ignored(client):
    """Verifies unhandled event types are acknowledged without crashing or throwing errors."""
    event_payload = {
        "id": "evt_unhandled_event_type",
        "type": "customer.source.created",
        "data": {"object": {}},
    }
    res = client.post("/api/billing/webhook", content=json.dumps(event_payload))
    assert res.status_code == 200
    assert res.json()["status"] == "processed"
    assert res.json()["action"] == "unhandled_event"


def test_mock_trigger_webhook_endpoint(client):
    """Verifies synthetic webhook triggering via POST /api/billing/mock/trigger-webhook."""
    user = register_user(client, "trigger_endpoint_user@example.com")
    tenant_id = user["tenant_id"]
    headers = {"Authorization": f"Bearer {user['access_token']}"}

    res = client.post(
        "/api/billing/mock/trigger-webhook",
        json={
            "id": "evt_synth_trigger",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "metadata": {"tenant_id": tenant_id, "tier": "pro"},
                    "tier": "pro",
                }
            },
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "processed"

    sub_res = client.get("/api/billing/subscription", headers=headers)
    assert sub_res.json()["tier"] == "pro"
    assert sub_res.json()["monthly_page_limit"] == 500
