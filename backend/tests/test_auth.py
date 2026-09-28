import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.database import Base, get_db

# Create an in-memory SQLite engine for isolated test runs
engine_test = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(autouse=True)
def setup_test_database():
    """Recreates all database tables before every test."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def client():
    """Provides a TestClient with overridden get_db dependency."""
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


def test_auth_registration_success(client):
    """Verifies standard user registration creates tenant, user, free subscription, and JWT token."""
    payload = {
        "email": "test_user_1@example.com",
        "password": "SecurePassword123!",
        "tier": "free",
        "full_name": "Test User One",
    }
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test_user_1@example.com"
    assert "token" in data
    assert "access_token" in data
    assert data["subscription_tier"] == "free"
    assert data["tenant_id"].startswith("ten_")
    assert data["id"].startswith("usr_")


def test_auth_duplicate_email_rejection(client):
    """Verifies that duplicate email registrations are rejected with HTTP 400."""
    payload = {
        "email": "duplicate@example.com",
        "password": "Password123!",
    }
    res1 = client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/auth/register", json=payload)
    assert res2.status_code == 400
    assert "already registered" in res2.json()["detail"].lower()


def test_auth_login_with_valid_credentials(client):
    """Verifies logging in with correct credentials returns valid JWT token."""
    client.post(
        "/api/auth/register",
        json={"email": "login_user@example.com", "password": "Password123!"},
    )
    res = client.post(
        "/api/auth/login",
        json={"email": "login_user@example.com", "password": "Password123!"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["email"] == "login_user@example.com"
    assert "token" in data
    assert len(data["token"]) > 20


def test_auth_login_with_invalid_password(client):
    """Verifies login failure on incorrect password."""
    client.post(
        "/api/auth/register",
        json={"email": "wrong_pwd@example.com", "password": "CorrectPassword123!"},
    )
    res = client.post(
        "/api/auth/login",
        json={"email": "wrong_pwd@example.com", "password": "WrongPassword!"},
    )
    assert res.status_code == 401
    assert "invalid" in res.json()["detail"].lower()


def test_auth_login_with_unknown_email(client):
    """Verifies login failure when user email does not exist."""
    res = client.post(
        "/api/auth/login",
        json={"email": "nonexistent@example.com", "password": "Password123!"},
    )
    assert res.status_code == 401


def test_auth_jwt_guard_and_me_endpoint(client):
    """Verifies JWT auth guard on protected /api/auth/me endpoint."""
    # 1. Without token -> 401
    unauth = client.get("/api/auth/me")
    assert unauth.status_code == 401

    # 2. With invalid token -> 401
    bad_token = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_garbage_token"})
    assert bad_token.status_code == 401

    # 3. With valid token -> 200
    reg = client.post(
        "/api/auth/register",
        json={"email": "me_user@example.com", "password": "Password123!"},
    )
    token = reg.json()["token"]
    auth = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert auth.status_code == 200
    me_data = auth.json()
    assert me_data["email"] == "me_user@example.com"
    assert me_data["role"] == "owner"
    assert me_data["subscription_tier"] == "free"


def test_auth_tenant_isolation_on_registration(client):
    """Verifies two different users receive isolated, unique tenant IDs."""
    u1 = client.post(
        "/api/auth/register",
        json={"email": "tenant1@example.com", "password": "Password123!"},
    ).json()
    u2 = client.post(
        "/api/auth/register",
        json={"email": "tenant2@example.com", "password": "Password123!"},
    ).json()

    assert u1["tenant_id"] != u2["tenant_id"]
    assert u1["tenant_id"].startswith("ten_")
    assert u2["tenant_id"].startswith("ten_")


def test_auth_logout_clears_session(client):
    """Verifies logout endpoint responds with success."""
    res = client.post("/api/auth/logout")
    assert res.status_code == 200
    assert res.json()["success"] is True
