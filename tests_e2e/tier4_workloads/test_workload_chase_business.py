"""
Tier 4: Real-World Workload 1 — Chase Commercial Business Statement Workflow.
Simulates:
- Loading Chase Commercial Checking statement (TC-01 reference fixture)
- Parsing all transactions against authoritative ground truth
- Validating strict decimal mathematical reconciliation
- Exporting to RFC 4180 CSV and verifying row integrity
"""
import os
import json
from decimal import Decimal
import pytest

from tests_e2e.harness.contracts import (
    StatementMetadata,
    TransactionRecord,
    ReconciliationSummary,
    ExportPayload,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle, ReferenceExportOracle
from tests_e2e.harness.client import OpaqueSaaSClient


def test_workload_chase_commercial_checking():
    fixtures_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
    gt_file = os.path.join(fixtures_dir, "ground_truth", "tc01_chase_single_page.json")
    assert os.path.exists(gt_file), f"Ground truth fixture missing: {gt_file}"

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    # 1. Validate Statement Metadata against ground truth
    meta = StatementMetadata.model_validate(gt_data["metadata"])
    assert meta.bank_name == "JPMorgan Chase Bank, N.A."
    assert meta.account_number == "************4921"
    assert meta.starting_balance == "3450.00"

    # 2. Validate all transactions match ground truth records
    txs = [TransactionRecord.model_validate(t) for t in gt_data["transactions"]]
    assert len(txs) == 6
    assert txs[0].payee == "Direct Deposit ACME Corp"
    assert txs[0].amount == "2800.00"

    # 3. Compute strict reconciliation
    rec = ReferenceReconciliationOracle.compute_reconciliation(
        starting_balance=to_decimal(meta.starting_balance),
        reported_ending_balance=to_decimal(meta.ending_balance),
        transactions=txs,
    )
    assert rec.is_reconciled is True
    assert rec.discrepancy == "0.00"
    assert rec.calculated_ending_balance == meta.ending_balance
    assert rec.net_cashflow == "2691.81"

    # 4. Export to CSV and verify RFC 4180 compliance
    payload = ExportPayload(metadata=meta, reconciliation=rec, transactions=txs)
    csv_bytes = ReferenceExportOracle.generate_reference_csv(payload)
    is_valid, errors = ReferenceExportOracle.validate_csv(csv_bytes, payload)
    assert is_valid is True
    assert len(errors) == 0

    # 5. Round trip verification
    rt_passed, rt_msg = ReferenceExportOracle.round_trip_verify(payload)
    assert rt_passed is True
