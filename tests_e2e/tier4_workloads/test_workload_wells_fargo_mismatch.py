"""
Tier 4: Real-World Workload 3 — Wells Fargo Two-Column Statement with Deliberate Discrepancy & Resolution.
Simulates:
- Loading Wells Fargo two-column statement (TC-03 fixture)
- Ingesting an artificial missing transaction discrepancy
- Running automatic diagnostics to detect missing gap
- Applying interactive resolution
- Proving full mathematical reconciliation
"""
import os
import json
from decimal import Decimal
import pytest

from tests_e2e.harness.contracts import (
    StatementMetadata,
    TransactionRecord,
    ReconciliationSummary,
    TransactionType,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle
from tests_e2e.harness.client import OpaqueSaaSClient


def test_workload_wells_fargo_two_column_with_discrepancy():
    fixtures_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")
    gt_file = os.path.join(fixtures_dir, "ground_truth", "tc03_wells_fargo_two_column.json")
    assert os.path.exists(gt_file)

    with open(gt_file, "r", encoding="utf-8") as f:
        gt_data = json.load(f)

    meta = StatementMetadata.model_validate(gt_data["metadata"])
    txs = [TransactionRecord.model_validate(t) for t in gt_data["transactions"]]

    # 1. First verify base statement is reconciled
    base_rec = ReferenceReconciliationOracle.compute_reconciliation(
        to_decimal(meta.starting_balance), to_decimal(meta.ending_balance), txs
    )
    assert base_rec.is_reconciled is True

    # 2. Inject artificial omission of Target Superstore ($88.40)
    omitted_tx = txs.pop(1)
    assert "Target" in omitted_tx.payee

    # 3. Recompute reconciliation with missing row
    mismatched_rec = ReferenceReconciliationOracle.compute_reconciliation(
        to_decimal(meta.starting_balance), to_decimal(meta.ending_balance), txs
    )
    assert mismatched_rec.is_reconciled is False
    assert mismatched_rec.discrepancy == "88.40"
    assert any("UNRECONCILED_DISCREPANCY" in f for f in mismatched_rec.diagnostic_flags)

    # 4. Resolve anomaly by re-inserting missing transaction
    txs.insert(1, omitted_tx)
    resolved_rec = ReferenceReconciliationOracle.compute_reconciliation(
        to_decimal(meta.starting_balance), to_decimal(meta.ending_balance), txs
    )
    assert resolved_rec.is_reconciled is True
    assert resolved_rec.discrepancy == "0.00"
