"""
Tier 4: Real-World Workload 2 — Bank of America Multi-Page Checking Statement.
Simulates:
- Loading Bank of America Multi-Page statement (TC-02 reference fixture)
- Validating large transaction volume (25+ transactions across pages)
- Continuous running balance verification across page boundaries
- Exporting to styled Excel .xlsx workbook
"""
import os
import io
import json
from decimal import Decimal
import pytest
import openpyxl

from tests_e2e.harness.contracts import (
    StatementMetadata,
    TransactionRecord,
    ReconciliationSummary,
    ExportPayload,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle, ReferenceExportOracle
from tests_e2e.harness.client import OpaqueSaaSClient


def test_workload_boa_multipage_checking():
    fixtures_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
    gt_file = os.path.join(fixtures_dir, "ground_truth", "tc02_boa_multi_page.json")
    assert os.path.exists(gt_file), f"Ground truth fixture missing: {gt_file}"

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    meta = StatementMetadata.model_validate(gt_data["metadata"])
    assert meta.bank_name == "Bank of America, N.A."
    assert meta.starting_balance == "12500.00"

    txs = [TransactionRecord.model_validate(t) for t in gt_data["transactions"]]
    assert len(txs) >= 25

    # Verify reconciliation and running balances
    rec = ReferenceReconciliationOracle.compute_reconciliation(
        starting_balance=to_decimal(meta.starting_balance),
        reported_ending_balance=to_decimal(meta.ending_balance),
        transactions=txs,
    )
    assert rec.is_reconciled is True
    assert rec.discrepancy == "0.00"

    # Export to Excel (.xlsx) and verify worksheet integrity
    client = OpaqueSaaSClient()
    payload = ExportPayload(metadata=meta, reconciliation=rec, transactions=txs)
    xlsx_bytes = client.export_data(payload, format_type="xlsx")

    is_valid, errors = ReferenceExportOracle.validate_xlsx(xlsx_bytes, payload)
    assert is_valid is True
    assert len(errors) == 0

    # Ensure all rows written to worksheet
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb["Transactions"]
    assert ws.max_row == len(txs) + 1  # 1 header + N rows
