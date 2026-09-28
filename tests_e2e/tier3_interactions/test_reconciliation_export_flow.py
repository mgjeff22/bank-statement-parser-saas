"""
Tier 3: Cross-Feature Interactions — Reconciliation Discrepancy -> Interactive Quick-Fix -> Multi-Format Export Flow.
Verifies:
- Statement loaded with deliberate sign inversion
- Discrepancy flagged: SUSPECTED_SIGN_INVERSION
- User applies quick-fix (flips type from CREDIT to DEBIT)
- Real-time reconciliation banner updates to is_reconciled=True
- Exporter outputs verified CSV, XLSX, and JSON
- Round-trip validation passes with zero corruption
"""
from decimal import Decimal
import io
import json
import pytest
import openpyxl

from tests_e2e.harness.contracts import (
    StatementMetadata,
    TransactionRecord,
    ReconciliationSummary,
    ExportPayload,
    TransactionType,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle, ReferenceExportOracle
from tests_e2e.harness.client import OpaqueSaaSClient


def test_i_discrepancy_quick_fix_and_export_flow():
    client = OpaqueSaaSClient()

    # 1. Setup statement with deliberate sign inversion ($100 debit misclassified as credit)
    starting_balance = "8000.00"
    reported_ending = "10355.00"
    txs = [
        TransactionRecord(id="tx_01", date="2026-09-02", payee="Consulting Fee", type=TransactionType.CREDIT, amount="2500.00", category="Income / Payroll", running_balance="10500.00"),
        TransactionRecord(id="tx_02", date="2026-09-08", payee="AWS Cloud Server", type=TransactionType.CREDIT, amount="100.00", category="Software & Subscriptions", running_balance="10400.00", has_anomaly=True, anomaly_type="SIGN_INVERSION"),
        TransactionRecord(id="tx_03", date="2026-09-15", payee="Staples Stationery", type=TransactionType.DEBIT, amount="45.00", category="Shopping & Retail", running_balance="10355.00"),
    ]

    # 2. Trigger reconciliation before fix
    r1 = client.trigger_reconciliation(starting_balance, reported_ending, txs)
    assert r1.is_reconciled is False
    assert r1.discrepancy == "200.00"
    assert any("SUSPECTED_SIGN_INVERSION" in f for f in r1.diagnostic_flags)

    # 3. Simulate User Quick-Fix click in Workspace UI
    # In tx_02, flip type from CREDIT to DEBIT and update running balances
    txs[1].type = TransactionType.DEBIT
    txs[1].has_anomaly = False
    txs[1].anomaly_type = None

    # 4. Trigger reconciliation banner update after fix
    r2 = client.trigger_reconciliation(starting_balance, reported_ending, txs)
    assert r2.is_reconciled is True
    assert r2.discrepancy == "0.00"
    assert r2.calculated_ending_balance == reported_ending
    assert len(r2.diagnostic_flags) == 0

    # 5. Build ExportPayload for reconciled statement
    meta = StatementMetadata(
        bank_name="PNC Commercial",
        account_number="************1190",
        statement_period_start="2026-09-01",
        statement_period_end="2026-09-30",
        starting_balance=starting_balance,
        ending_balance=reported_ending,
    )
    payload = ExportPayload(metadata=meta, reconciliation=r2, transactions=txs)

    # 6. Verify CSV export
    csv_bytes = client.export_data(payload, format_type="csv")
    csv_valid, csv_errors = ReferenceExportOracle.validate_csv(csv_bytes, payload)
    assert csv_valid is True
    assert len(csv_errors) == 0

    # 7. Verify XLSX export
    xlsx_bytes = client.export_data(payload, format_type="xlsx")
    xlsx_valid, xlsx_errors = ReferenceExportOracle.validate_xlsx(xlsx_bytes, payload)
    assert xlsx_valid is True
    assert len(xlsx_errors) == 0

    # 8. Verify JSON export & Round-trip
    json_bytes = client.export_data(payload, format_type="json")
    recovered_data = json.loads(json_bytes.decode("utf-8"))
    recovered_payload = ExportPayload.model_validate(recovered_data)
    assert recovered_payload.reconciliation.is_reconciled is True
    assert recovered_payload.transactions[1].type == TransactionType.DEBIT

    rt_pass, rt_msg = ReferenceExportOracle.round_trip_verify(payload)
    assert rt_pass is True
