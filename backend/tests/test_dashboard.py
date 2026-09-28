import io
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db
from app.services.quota import record_usage

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


def test_dashboard_stats_empty_account(client):
    """Verifies default statistics for a freshly registered user account."""
    reg = client.post(
        "/api/auth/register",
        json={"email": "fresh_dash@example.com", "password": "Password123!", "tier": "free"},
    ).json()
    token = reg["token"]

    res = client.get("/api/dashboard/stats", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    stats = res.json()
    assert stats["pages_used"] == 0
    assert stats["monthly_limit"] == 5
    assert stats["remaining_pages"] == 5
    assert stats["percentage_used"] == 0.0
    assert stats["tier"] == "free"
    assert stats["statement_count"] == 0
    assert stats["warning"] is False


def test_dashboard_stats_calculation_and_warning_threshold(client, db_session):
    """Verifies stats percentage calculation and warning trigger at >= 80% quota usage."""
    reg = client.post(
        "/api/auth/register",
        json={"email": "warn_dash@example.com", "password": "Password123!", "tier": "free"},
    ).json()
    token = reg["token"]
    tenant_id = reg["tenant_id"]

    # Consume 4 out of 5 pages (80.0%)
    record_usage(tenant_id, 4, db_session)

    res = client.get("/api/dashboard/stats", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    stats = res.json()
    assert stats["pages_used"] == 4
    assert stats["monthly_limit"] == 5
    assert stats["remaining_pages"] == 1
    assert stats["percentage_used"] == 80.0
    assert stats["warning"] is True


def test_dashboard_history_retrieval_and_statement_lifecycle(client):
    """Verifies that uploaded statements appear in history and can be inspected or deleted."""
    reg = client.post(
        "/api/auth/register",
        json={"email": "hist_dash@example.com", "password": "Password123!"},
    ).json()
    token = reg["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Upload single-page statement
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"

    upload_res = client.post(
        "/api/statements/upload",
        files={"file": ("history_test.pdf", io.BytesIO(pdf_content), "application/pdf")},
        data={"filename": "history_test.pdf"},
        headers=headers,
    )
    assert upload_res.status_code == 200
    stmt_data = upload_res.json()
    stmt_id = stmt_data["statement_id"]

    # Check /api/dashboard/history
    history_res = client.get("/api/dashboard/history", headers=headers)
    assert history_res.status_code == 200
    history = history_res.json()
    assert len(history) == 1
    assert history[0]["statement_id"] == stmt_id
    assert history[0]["filename"] == "history_test.pdf"
    assert history[0]["status"] in ["completed", "error"]

    # Check /api/statements/history alias
    alias_res = client.get("/api/statements/history", headers=headers)
    assert alias_res.status_code == 200
    assert len(alias_res.json()) == 1

    # Check individual statement retrieval
    get_res = client.get(f"/api/statements/{stmt_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["statement_id"] == stmt_id

    # Check delete statement
    del_res = client.delete(f"/api/statements/{stmt_id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # History should now be empty
    after_del = client.get("/api/dashboard/history", headers=headers).json()
    assert len(after_del) == 0

    # Deleting non-existent statement returns success: False
    del_nonexistent = client.delete("/api/statements/non_existent_id", headers=headers)
    assert del_nonexistent.json()["success"] is False
