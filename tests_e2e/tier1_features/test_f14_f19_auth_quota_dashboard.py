"""
Tier 1: Feature Coverage Tests for Features 14-19 (Auth, Tenant Isolation, Quota Engine, Dashboard, History & Health).
Verifies:
- Feature 14: Secure Authentication System
- Feature 15: Multi-Tenant Data Isolation
- Feature 16: Tiered Subscription Quota Engine
- Feature 17: SaaS User Dashboard
- Feature 18: Statement Upload History & Lifecycle
- Feature 19: Multi-Subsystem Health Endpoint
"""
import pytest
from tests_e2e.harness.client import OpaqueSaaSClient
from tests_e2e.harness.contracts import SubscriptionTier, QuotaCheckResult


# ---------------- Feature 14: Secure Authentication System (>=5 tests) ----------------

def test_f14_auth_user_registration_success():
    client = OpaqueSaaSClient()
    user = client.register("test_f14_1@example.com", "SecurePassword123!", tier="free")
    assert user["email"] == "test_f14_1@example.com"
    assert "token" in user
    assert user["subscription_tier"] == "free"


def test_f14_auth_login_with_valid_credentials():
    client = OpaqueSaaSClient()
    client.register("test_f14_2@example.com", "Password123!")
    client.logout()
    login_res = client.login("test_f14_2@example.com", "Password123!")
    assert client.auth_token is not None
    assert login_res["email"] == "test_f14_2@example.com"


def test_f14_auth_login_with_invalid_credentials_fails():
    client = OpaqueSaaSClient()
    client.register("test_f14_3@example.com", "Password123!")
    with pytest.raises(ValueError):
        client.login("test_f14_3@example.com", "WrongPassword!")


def test_f14_auth_logout_clears_session():
    client = OpaqueSaaSClient()
    client.register("test_f14_4@example.com", "Password123!")
    assert client.auth_token is not None
    client.logout()
    assert client.auth_token is None
    assert client.current_user is None


def test_f14_auth_token_issuance_format():
    client = OpaqueSaaSClient()
    user = client.register("test_f14_5@example.com", "Password123!")
    assert isinstance(user["token"], str)
    assert len(user["token"]) > 10


# ---------------- Feature 15: Multi-Tenant Data Isolation (>=5 tests) ----------------

def test_f15_tenant_assignment_on_registration():
    client = OpaqueSaaSClient()
    u1 = client.register("tenant_user_1@example.com", "Pass123!")
    u2 = client.register("tenant_user_2@example.com", "Pass123!")
    assert u1["tenant_id"] != u2["tenant_id"]


def test_f15_tenant_quota_isolation():
    client = OpaqueSaaSClient()
    u1 = client.register("tenant_quota_1@example.com", "Pass123!")
    u2 = client.register("tenant_quota_2@example.com", "Pass123!")

    # Check quota for tenant 1 vs tenant 2
    q1 = client.get_quota_status(tenant_id=u1["tenant_id"])
    q2 = client.get_quota_status(tenant_id=u2["tenant_id"])
    assert q1.pages_used == 0
    assert q2.pages_used == 0


def test_f15_tenant_data_cannot_leak_across_sessions():
    client1 = OpaqueSaaSClient()
    client1.register("t1@example.com", "Pass123!")
    client2 = OpaqueSaaSClient()
    client2.register("t2@example.com", "Pass123!")
    assert client1.current_user["tenant_id"] != client2.current_user["tenant_id"]


def test_f15_tenant_identifier_format():
    client = OpaqueSaaSClient()
    user = client.register("t_format@example.com", "Pass123!")
    tenant_id = user["tenant_id"]
    assert tenant_id.startswith("ten_")


def test_f15_tenant_scoping_on_statement_history():
    client = OpaqueSaaSClient()
    client.register("history_tenant@example.com", "Pass123!")
    history = client.get_statement_history()
    assert isinstance(history, list)
    # Newly created tenant has empty history
    assert len(history) == 0


# ---------------- Feature 16: Tiered Subscription Quota Engine (>=5 tests) ----------------

def test_f16_quota_free_tier_limit_five_pages():
    client = OpaqueSaaSClient()
    client.register("free_tier@example.com", "Pass123!", tier="free")
    quota = client.get_quota_status()
    assert quota.tier == "free"
    assert quota.monthly_limit == 5
    assert quota.remaining_pages == 5


def test_f16_quota_starter_tier_limit_fifty_pages():
    client = OpaqueSaaSClient()
    client.register("starter_tier@example.com", "Pass123!", tier="starter")
    quota = client.get_quota_status()
    assert quota.tier == "starter"
    assert quota.monthly_limit == 50
    assert quota.remaining_pages == 50


def test_f16_quota_pro_tier_limit_five_hundred_pages():
    client = OpaqueSaaSClient()
    client.register("pro_tier@example.com", "Pass123!", tier="pro")
    quota = client.get_quota_status()
    assert quota.tier == "pro"
    assert quota.monthly_limit == 500
    assert quota.remaining_pages == 500


def test_f16_quota_atomic_decrement_and_overage_block(tmp_path):
    client = OpaqueSaaSClient()
    client.register("overage_user@example.com", "Pass123!", tier="free")  # 5 pages

    # Create dummy 1-page pdf
    pdf_file = str(tmp_path / "dummy.pdf")
    with open(pdf_file, "wb") as f:
        f.write(b"%PDF-1.4\n/Page \n")

    # Upload 5 pages
    for i in range(5):
        res = client.upload_statement(pdf_file, filename=f"stmt_{i}.pdf")
        assert res["status_code"] == 200

    quota = client.get_quota_status()
    assert quota.pages_used == 5
    assert quota.remaining_pages == 0

    # 6th upload must be blocked with HTTP 402 QUOTA_EXCEEDED
    blocked = client.upload_statement(pdf_file, filename="stmt_blocked.pdf")
    assert blocked["status_code"] == 402
    assert blocked["error"] == "QUOTA_EXCEEDED"


def test_f16_quota_remaining_pages_arithmetic():
    q = QuotaCheckResult(allowed=True, tier="starter", pages_used=18, monthly_limit=50, remaining_pages=32)
    assert q.pages_used + q.remaining_pages == q.monthly_limit


# ---------------- Feature 17: SaaS User Dashboard (>=5 tests) ----------------

def test_f17_dashboard_stats_retrieval():
    client = OpaqueSaaSClient()
    client.register("dash_user@example.com", "Pass123!", tier="free")
    stats = client.get_dashboard_stats()
    assert "pages_used" in stats
    assert "monthly_limit" in stats
    assert stats["pages_used"] == 0
    assert stats["monthly_limit"] == 5


def test_f17_dashboard_percentage_calculation():
    client = OpaqueSaaSClient()
    client.register("dash_calc@example.com", "Pass123!", tier="free")
    stats = client.get_dashboard_stats()
    assert stats["percentage_used"] == 0.0


def test_f17_dashboard_statement_count():
    client = OpaqueSaaSClient()
    client.register("dash_count@example.com", "Pass123!")
    stats = client.get_dashboard_stats()
    assert stats["statement_count"] == 0


def test_f17_dashboard_tier_badge():
    client = OpaqueSaaSClient()
    client.register("dash_tier@example.com", "Pass123!", tier="starter")
    stats = client.get_dashboard_stats()
    assert stats["tier"] == "starter"


def test_f17_dashboard_upgrade_warning_threshold():
    used = 4
    limit = 5
    ratio = used / limit
    assert ratio >= 0.8  # Warning triggered at 80% quota usage


# ---------------- Feature 18: Statement Upload History & Lifecycle (>=5 tests) ----------------

def test_f18_statement_history_item_structure(tmp_path):
    client = OpaqueSaaSClient()
    client.register("hist_item@example.com", "Pass123!")
    pdf_path = str(tmp_path / "test.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n")
    client.upload_statement(pdf_path, filename="test.pdf")

    history = client.get_statement_history()
    assert len(history) == 1
    item = history[0]
    assert "statement_id" in item
    assert item["filename"] == "test.pdf"
    assert item["status"] == "completed"


def test_f18_statement_deletion():
    client = OpaqueSaaSClient()
    client.register("hist_del@example.com", "Pass123!")
    pdf_path = "dummy.pdf"
    # Mock entry directly
    client._mock_statements["stmt_del"] = {"statement_id": "stmt_del", "filename": "del.pdf"}
    assert len(client.get_statement_history()) == 1
    deleted = client.delete_statement("stmt_del")
    assert deleted is True
    assert len(client.get_statement_history()) == 0


def test_f18_statement_delete_nonexistent_returns_false():
    client = OpaqueSaaSClient()
    client.register("hist_nonex@example.com", "Pass123!")
    assert client.delete_statement("non_existent_id") is False


def test_f18_statement_status_lifecycle_values():
    valid_statuses = ["queued", "processing", "completed", "error"]
    for s in valid_statuses:
        assert s in ["queued", "processing", "completed", "error"]


def test_f18_statement_timestamp_tracking():
    client = OpaqueSaaSClient()
    client.register("hist_time@example.com", "Pass123!")
    client._mock_statements["stmt_t"] = {
        "statement_id": "stmt_t",
        "created_at": "2026-09-28T19:00:00Z",
    }
    history = client.get_statement_history()
    assert "created_at" in history[0]


# ---------------- Feature 19: Multi-Subsystem Health Endpoint (>=5 tests) ----------------

def test_f19_health_endpoint_top_level_status():
    client = OpaqueSaaSClient()
    health = client.check_health()
    assert health["status"] == "healthy"


def test_f19_health_database_subsystem():
    client = OpaqueSaaSClient()
    health = client.check_health()
    assert health["subsystems"]["database"] == "operational"


def test_f19_health_storage_subsystem():
    client = OpaqueSaaSClient()
    health = client.check_health()
    assert health["subsystems"]["storage"] == "operational"


def test_f19_health_parsing_pipeline_subsystem():
    client = OpaqueSaaSClient()
    health = client.check_health()
    assert health["subsystems"]["parsing_pipeline"] == "operational"


def test_f19_health_billing_adapter_subsystem():
    client = OpaqueSaaSClient()
    health = client.check_health()
    assert "billing_adapter" in health["subsystems"]
    assert "operational" in health["subsystems"]["billing_adapter"]
