"""
Tier 3: Cross-Feature Interactions — Quota Limit & Mock Billing Upgrade Lifecycle.
Verifies:
- Free user depletes 5-page monthly quota
- Attempted 6th upload returns HTTP 402 QUOTA_EXCEEDED
- User creates checkout session and triggers mock upgrade to Starter
- Webhook elevates quota to 50 pages atomically
- Retried upload succeeds immediately
"""
import pytest
from tests_e2e.harness.client import OpaqueSaaSClient


def test_i_quota_depletion_to_billing_upgrade_flow(tmp_path):
    client = OpaqueSaaSClient()
    user = client.register("billing_quota_user@example.com", "Password123!", tier="free")
    tenant_id = user["tenant_id"]

    # 1. Verify initial quota
    quota = client.get_quota_status()
    assert quota.tier == "free"
    assert quota.remaining_pages == 5

    # 2. Upload 5 pages
    pdf_path = str(tmp_path / "page.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n/Page \n")

    for i in range(5):
        res = client.upload_statement(pdf_path, filename=f"stmt_{i}.pdf")
        assert res["status_code"] == 200

    # 3. Verify quota fully exhausted
    quota_exhausted = client.get_quota_status()
    assert quota_exhausted.remaining_pages == 0

    # 4. Attempt 6th upload -> must return HTTP 402
    blocked_res = client.upload_statement(pdf_path, filename="stmt_blocked.pdf")
    assert blocked_res["status_code"] == 402
    assert blocked_res["error"] == "QUOTA_EXCEEDED"

    # 5. Create checkout session for Starter tier
    checkout_res = client.create_checkout_session(price_tier="starter", interval="month")
    assert "cs_test_" in checkout_res["session_id"]

    # 6. Simulate successful Stripe webhook: checkout.session.completed
    webhook_res = client.process_webhook(
        event_id="evt_test_upgrade_1",
        event_type="checkout.session.completed",
        data_object={"tier": "starter"},
    )
    assert webhook_res["status"] == "processed"

    # 7. Verify quota elevated to 50 pages
    quota_upgraded = client.get_quota_status()
    assert quota_upgraded.tier == "starter"
    assert quota_upgraded.monthly_limit == 50
    assert quota_upgraded.remaining_pages == 45  # 50 limit - 5 previously used

    # 8. Retry upload -> must succeed now!
    retry_res = client.upload_statement(pdf_path, filename="stmt_unblocked.pdf")
    assert retry_res["status_code"] == 200
    assert retry_res["status"] == "completed"
