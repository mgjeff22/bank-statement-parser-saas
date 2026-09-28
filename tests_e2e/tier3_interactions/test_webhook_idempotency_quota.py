"""
Tier 3: Cross-Feature Interactions — Webhook Idempotency & Quota Metering Interaction.
Verifies:
- Concurrent / duplicate Stripe webhook deliveries
- Processed events table deduplication
- Quota reset occurs exactly once
- Zero side-effects from replayed payloads
"""
import pytest
from tests_e2e.harness.client import OpaqueSaaSClient


def test_i_webhook_idempotency_protects_quota():
    client = OpaqueSaaSClient()
    client.register("idempotent_user@example.com", "Pass123!", tier="starter")
    t_id = client.current_user["tenant_id"]

    # Consume 30 pages
    client._mock_quotas[t_id]["pages_used"] = 30
    assert client.get_quota_status().pages_used == 30

    # Stripe delivers invoice.payment_succeeded
    event_id = "evt_invoice_annual_2026"
    res1 = client.process_webhook(
        event_id=event_id,
        event_type="invoice.payment_succeeded",
        data_object={"amount_paid": 19000},
    )
    assert res1["status"] == "processed"
    assert client.get_quota_status().pages_used == 0  # Reset to 0

    # Simulate user processes 10 pages under the new cycle
    client._mock_quotas[t_id]["pages_used"] = 10
    assert client.get_quota_status().pages_used == 10

    # Network replay delivers duplicate webhook event with same event_id
    res2 = client.process_webhook(
        event_id=event_id,
        event_type="invoice.payment_succeeded",
        data_object={"amount_paid": 19000},
    )
    assert res2["status"] == "ignored"
    assert res2["reason"] == "duplicate_event_id"

    # CRITICAL: Quota usage must NOT be erroneously reset again; it must remain at 10!
    assert client.get_quota_status().pages_used == 10
