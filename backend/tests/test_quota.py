import io
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.services.quota import (
    check_quota,
    record_usage,
    refund_usage,
    get_or_create_quota,
)

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


def test_free_tier_five_page_limit(client):
    """Verifies that free tier accounts are initialized with a 5-page monthly limit."""
    res = client.post(
        "/api/auth/register",
        json={"email": "free_user@example.com", "password": "Password123!", "tier": "free"},
    )
    assert res.status_code == 201
    user = res.json()

    quota_res = client.get(
        f"/api/dashboard/quota?tenant_id={user['tenant_id']}",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert quota_res.status_code == 200
    q = quota_res.json()
    assert q["tier"] == "free"
    assert q["monthly_limit"] == 5
    assert q["pages_used"] == 0
    assert q["remaining_pages"] == 5
    assert q["allowed"] is True


def test_starter_tier_fifty_page_limit(client):
    """Verifies that starter tier accounts receive a 50-page monthly limit."""
    res = client.post(
        "/api/auth/register",
        json={"email": "starter_user@example.com", "password": "Password123!", "tier": "starter"},
    )
    assert res.status_code == 201
    user = res.json()

    quota_res = client.get(
        f"/api/dashboard/quota?tenant_id={user['tenant_id']}",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert quota_res.status_code == 200
    q = quota_res.json()
    assert q["tier"] == "starter"
    assert q["monthly_limit"] == 50
    assert q["remaining_pages"] == 50


def test_pro_tier_five_hundred_page_limit(client):
    """Verifies that pro tier accounts receive a 500-page monthly limit."""
    res = client.post(
        "/api/auth/register",
        json={"email": "pro_user@example.com", "password": "Password123!", "tier": "pro"},
    )
    assert res.status_code == 201
    user = res.json()

    quota_res = client.get(
        f"/api/dashboard/quota?tenant_id={user['tenant_id']}",
        headers={"Authorization": f"Bearer {user['token']}"},
    )
    assert quota_res.status_code == 200
    q = quota_res.json()
    assert q["tier"] == "pro"
    assert q["monthly_limit"] == 500
    assert q["remaining_pages"] == 500


def test_atomic_decrement_and_overage_block_service(client, db_session):
    """Directly tests atomic quota reservation and overage rejection via service layer."""
    res = client.post(
        "/api/auth/register",
        json={"email": "atomic_svc@example.com", "password": "Password123!", "tier": "free"},
    ).json()
    tenant_id = res["tenant_id"]

    # Consume 3 pages
    q1 = record_usage(tenant_id, 3, db_session)
    assert q1.pages_used == 3

    # Consume remaining 2 pages
    q2 = record_usage(tenant_id, 2, db_session)
    assert q2.pages_used == 5

    # 1 more page must fail with HTTP 402 QUOTA_EXCEEDED
    with pytest.raises(HTTPException) as exc_info:
        check_quota(tenant_id, 1, db_session)
    assert exc_info.value.status_code == 402
    assert exc_info.value.detail["error"] == "QUOTA_EXCEEDED"
    assert exc_info.value.detail["pages_used"] == 5
    assert exc_info.value.detail["remaining_pages"] == 0


def test_upload_endpoint_overage_rejection_http_402(client):
    """Uploads statements up to limit and asserts that subsequent upload returns HTTP 402."""
    res = client.post(
        "/api/auth/register",
        json={"email": "upload_overage@example.com", "password": "Password123!", "tier": "free"},
    ).json()
    token = res["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload 5 single-page files (limit is 5)
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"

    for i in range(5):
        resp = client.post(
            "/api/statements/upload",
            files={"file": (f"stmt_{i}.pdf", io.BytesIO(pdf_content), "application/pdf")},
            data={"filename": f"stmt_{i}.pdf"},
            headers=headers,
        )
        assert resp.status_code == 200, f"Upload {i} failed: {resp.text}"

    # 6th upload must return HTTP 402
    blocked = client.post(
        "/api/statements/upload",
        files={"file": ("stmt_blocked.pdf", io.BytesIO(pdf_content), "application/pdf")},
        data={"filename": "stmt_blocked.pdf"},
        headers=headers,
    )
    assert blocked.status_code == 402
    err_body = blocked.json()
    assert err_body["error"] == "QUOTA_EXCEEDED"
    assert err_body["pages_used"] == 5
    assert err_body["remaining_pages"] == 0


def test_refund_usage_on_error(client, db_session):
    """Verifies that refund_usage rolls back quota usage correctly."""
    res = client.post(
        "/api/auth/register",
        json={"email": "refund_user@example.com", "password": "Password123!", "tier": "free"},
    ).json()
    tenant_id = res["tenant_id"]

    # Consume 4 pages
    record_usage(tenant_id, 4, db_session)
    quota = get_or_create_quota(tenant_id, db_session)
    assert quota.pages_used == 4

    # Simulate pipeline error compensation refund
    refund_usage(tenant_id, 4, db_session)
    refreshed = get_or_create_quota(tenant_id, db_session)
    assert refreshed.pages_used == 0
