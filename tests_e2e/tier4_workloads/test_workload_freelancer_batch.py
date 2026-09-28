"""
Tier 4: Real-World Workload 4 — Freelancer Monthly Statement Batch Ingestion & Quota Governance.
Simulates:
- Freelancer uploading multi-month client statements in batch
- Tracking monthly consumption percentage on dashboard
- Verifying atomic quota increments
- Inspecting upload history table
"""
import os
import pytest
from tests_e2e.harness.client import OpaqueSaaSClient


def test_workload_freelancer_batch_upload_and_quota(tmp_path):
    client = OpaqueSaaSClient()
    user = client.register("freelancer_sarah@example.com", "StudioPass2026!", tier="starter")  # 50 page limit

    # Check initial dashboard
    stats_0 = client.get_dashboard_stats()
    assert stats_0["pages_used"] == 0
    assert stats_0["statement_count"] == 0

    # Create synthetic 2-page PDF
    pdf_path = str(tmp_path / "freelance_stmt.pdf")
    with open(pdf_path, "wb") as f:
        f.write(b"%PDF-1.4\n/Page \n/Page \n")  # 2 pages

    # Upload 4 consecutive monthly statements (2 pages each = 8 pages)
    for m in ["Jan", "Feb", "Mar", "Apr"]:
        res = client.upload_statement(pdf_path, filename=f"statement_{m}_2026.pdf")
        assert res["status_code"] == 200
        assert res["status"] == "completed"

    # Verify quota and dashboard updates
    quota = client.get_quota_status()
    assert quota.pages_used == 8
    assert quota.remaining_pages == 42
    assert quota.monthly_limit == 50

    stats_final = client.get_dashboard_stats()
    assert stats_final["pages_used"] == 8
    assert stats_final["statement_count"] == 4
    assert stats_final["percentage_used"] == 16.0  # 8 / 50 * 100

    # Verify statement history list contains all 4 uploads
    history = client.get_statement_history()
    assert len(history) == 4
    filenames = [item["filename"] for item in history]
    assert "statement_Jan_2026.pdf" in filenames
    assert "statement_Apr_2026.pdf" in filenames
