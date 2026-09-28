"""
Tier 4: Real-World Workload 5 — Full SaaS Subscription Upgrade & Customer Portal Lifecycle.
Simulates:
- User registers on Free plan
- Exhausts 5-page quota limit
- Creates Stripe Checkout session for Pro annual tier
- Webhook elevates subscription and sets 500-page monthly limit
- High-volume parsing executes under new plan
- Customer accesses billing portal and later cancels
- Webhook safely resets user back to Free tier
"""
import pytest
from tests_e2e.harness.client import OpaqueSaaSClient


def test_workload_saas_user_upgrade_lifecycle(tmp_path):
    client = OpaqueSaaSClient()

    # 1. User registration on Free tier
    user = client.register("alex_cpa@example.com", "AccountingPro2026!", tier="free")
    assert user["subscription_tier"] == "free"
    assert client.get_quota_status().monthly_limit == 5

    # 2. Upload dummy statement exhausting 5 pages
    pdf_file = str(tmp_path / "1pg.pdf")
    with open(pdf_file, "wb") as f:
        f.write(b"%PDF-1.4\n/Page \n")

    for i in range(5):
        client.upload_statement(pdf_file)
    assert client.get_quota_status().remaining_pages == 0

    # 3. Create Checkout Session for Pro tier
    checkout = client.create_checkout_session(price_tier="pro", interval="year")
    assert "cs_test_pro" in checkout["session_id"]

    # 4. Trigger Webhook upgrade to Pro
    wh_res = client.process_webhook(
        event_id="evt_upgrade_pro_annual",
        event_type="checkout.session.completed",
        data_object={"tier": "pro", "interval": "year"},
    )
    assert wh_res["status"] == "processed"

    # 5. Verify Pro quota: 500 pages
    quota_pro = client.get_quota_status()
    assert quota_pro.tier == "pro"
    assert quota_pro.monthly_limit == 500
    assert quota_pro.remaining_pages == 495

    # 6. Customer accesses self-service portal
    portal = client.create_portal_session()
    assert portal["portal_url"].startswith("https://billing.stripe.com/")

    # 7. Customer cancels subscription -> triggers customer.subscription.deleted
    cancel_res = client.process_webhook(
        event_id="evt_cancel_pro",
        event_type="customer.subscription.deleted",
        data_object={},
    )
    assert cancel_res["status"] == "processed"

    # 8. Verify clean downgrade back to Free tier
    quota_downgraded = client.get_quota_status()
    assert quota_downgraded.tier == "free"
    assert quota_downgraded.monthly_limit == 5
