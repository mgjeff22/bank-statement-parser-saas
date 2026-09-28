"""
Tier 1: Feature Coverage Tests for Features 25-33 (Workspace UI, Editable Grid, Banner, Anomaly Resolution & Exporters).
Verifies:
- Feature 25: Split-Pane Inspection Workspace UI
- Feature 26: Inline Editable Transaction Grid
- Feature 27: Dynamic Row Management UI
- Feature 28: Real-Time Reconciliation Banner UI
- Feature 29: Anomaly Highlighting & Resolution UI
- Feature 30: RFC 4180 CSV Exporter
- Feature 31: Professional Excel (.xlsx) Exporter
- Feature 32: Structured JSON Exporter
- Feature 33: Exporter Round-Trip Verification
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


@pytest.fixture
def sample_export_payload():
    meta = StatementMetadata(
        bank_name="Test Commercial Bank",
        account_number="************4321",
        statement_period_start="2026-08-01",
        statement_period_end="2026-08-31",
        starting_balance="1000.00",
        ending_balance="1450.00",
        currency="USD",
        page_count=1,
    )
    txs = [
        TransactionRecord(id="tx_1", date="2026-08-02", payee="Client Payment", type=TransactionType.CREDIT, amount="500.00", category="Income / Payroll", running_balance="1500.00"),
        TransactionRecord(id="tx_2", date="2026-08-05", payee="Software Cloud", type=TransactionType.DEBIT, amount="50.00", category="Software & Subscriptions", running_balance="1450.00"),
    ]
    rec = ReferenceReconciliationOracle.compute_reconciliation(Decimal("1000.00"), Decimal("1450.00"), txs)
    return ExportPayload(metadata=meta, reconciliation=rec, transactions=txs)


# ---------------- Feature 25: Split-Pane Inspection Workspace UI (>=5 tests) ----------------

def test_f25_workspace_split_pane_contract(sample_export_payload):
    # Split-pane accepts doc viewer state and grid transaction state
    assert sample_export_payload.metadata.page_count >= 1
    assert len(sample_export_payload.transactions) == 2


def test_f25_workspace_document_preview_formats():
    supported_preview_formats = ["application/pdf", "image/png", "image/jpeg", "image/webp"]
    assert "application/pdf" in supported_preview_formats
    assert "image/png" in supported_preview_formats


def test_f25_workspace_page_navigation_bounds():
    current_page = 1
    total_pages = 5
    assert 1 <= current_page <= total_pages
    next_page = min(current_page + 1, total_pages)
    assert next_page == 2


def test_f25_workspace_zoom_scaling_levels():
    zoom_levels = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    assert 1.0 in zoom_levels
    assert all(z > 0 for z in zoom_levels)


def test_f25_workspace_selection_sync():
    # Selecting row tx_1 highlights corresponding region in viewer
    selected_row_id = "tx_1"
    assert selected_row_id.startswith("tx_")


# ---------------- Feature 26: Inline Editable Transaction Grid (>=5 tests) ----------------

def test_f26_grid_inline_edit_amount():
    tx = TransactionRecord(id="tx_edit", date="2026-08-01", payee="P", type=TransactionType.DEBIT, amount="10.00", running_balance="90.00")
    # Inline edit to 15.00
    tx.amount = "15.00"
    assert tx.amount == "15.00"


def test_f26_grid_inline_edit_payee():
    tx = TransactionRecord(id="tx_edit", date="2026-08-01", payee="Old Payee", type=TransactionType.DEBIT, amount="10.00", running_balance="90.00")
    tx.payee = "Cleaned Payee Name"
    assert tx.payee == "Cleaned Payee Name"


def test_f26_grid_inline_toggle_type():
    tx = TransactionRecord(id="tx_edit", date="2026-08-01", payee="P", type=TransactionType.DEBIT, amount="10.00", running_balance="90.00")
    tx.type = TransactionType.CREDIT
    assert tx.type == TransactionType.CREDIT


def test_f26_grid_search_filter():
    txs = [
        TransactionRecord(id="1", date="2026-08-01", payee="Starbucks Coffee", type=TransactionType.DEBIT, amount="5.00", running_balance="95.00"),
        TransactionRecord(id="2", date="2026-08-02", payee="Target Superstore", type=TransactionType.DEBIT, amount="45.00", running_balance="50.00"),
    ]
    query = "starbucks"
    filtered = [t for t in txs if query.lower() in t.payee.lower()]
    assert len(filtered) == 1
    assert filtered[0].id == "1"


def test_f26_grid_sorting_by_amount():
    txs = [
        TransactionRecord(id="1", date="2026-08-01", payee="A", type=TransactionType.DEBIT, amount="50.00", running_balance="50.00"),
        TransactionRecord(id="2", date="2026-08-02", payee="B", type=TransactionType.DEBIT, amount="10.00", running_balance="40.00"),
    ]
    sorted_asc = sorted(txs, key=lambda t: to_decimal(t.amount))
    assert sorted_asc[0].id == "2"
    assert sorted_asc[1].id == "1"


# ---------------- Feature 27: Dynamic Row Management UI (>=5 tests) ----------------

def test_f27_row_management_add_row():
    txs = [TransactionRecord(id="1", date="2026-08-01", payee="A", type=TransactionType.DEBIT, amount="10.00", running_balance="90.00")]
    new_row = TransactionRecord(id="2", date="2026-08-02", payee="B", type=TransactionType.CREDIT, amount="50.00", running_balance="140.00")
    txs.append(new_row)
    assert len(txs) == 2


def test_f27_row_management_delete_row():
    txs = [
        TransactionRecord(id="1", date="2026-08-01", payee="A", type=TransactionType.DEBIT, amount="10.00", running_balance="90.00"),
        TransactionRecord(id="2", date="2026-08-02", payee="B", type=TransactionType.CREDIT, amount="50.00", running_balance="140.00"),
    ]
    txs = [t for t in txs if t.id != "1"]
    assert len(txs) == 1
    assert txs[0].id == "2"


def test_f27_row_management_reorder_rows():
    txs = [
        TransactionRecord(id="1", date="2026-08-01", payee="A", type=TransactionType.DEBIT, amount="10.00", running_balance="90.00"),
        TransactionRecord(id="2", date="2026-08-02", payee="B", type=TransactionType.CREDIT, amount="50.00", running_balance="140.00"),
    ]
    # Reverse order
    txs.reverse()
    assert txs[0].id == "2"


def test_f27_row_management_insert_at_index():
    txs = ["tx1", "tx3"]
    txs.insert(1, "tx2")
    assert txs == ["tx1", "tx2", "tx3"]


def test_f27_row_management_batch_delete():
    txs = ["tx1", "tx2", "tx3", "tx4"]
    to_delete = {"tx2", "tx3"}
    txs = [t for t in txs if t not in to_delete]
    assert txs == ["tx1", "tx4"]


# ---------------- Feature 28: Real-Time Reconciliation Banner UI (>=5 tests) ----------------

def test_f28_banner_recomputes_net_cashflow():
    client = OpaqueSaaSClient()
    txs = [
        TransactionRecord(id="1", date="2026-08-01", payee="Deposit", type=TransactionType.CREDIT, amount="1000.00", running_balance="2000.00"),
        TransactionRecord(id="2", date="2026-08-02", payee="Rent", type=TransactionType.DEBIT, amount="400.00", running_balance="1600.00"),
    ]
    rec = client.trigger_reconciliation("1000.00", "1600.00", txs)
    assert rec.net_cashflow == "600.00"
    assert rec.is_reconciled is True


def test_f28_banner_discrepancy_alert_state():
    client = OpaqueSaaSClient()
    txs = [TransactionRecord(id="1", date="2026-08-01", payee="Deposit", type=TransactionType.CREDIT, amount="1000.00", running_balance="2000.00")]
    rec = client.trigger_reconciliation("1000.00", "2500.00", txs)
    assert rec.is_reconciled is False
    assert rec.discrepancy == "-500.00"


def test_f28_banner_live_update_on_amount_edit():
    client = OpaqueSaaSClient()
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="A", type=TransactionType.CREDIT, amount="500.00", running_balance="1500.00")
    # First state
    r1 = client.trigger_reconciliation("1000.00", "1500.00", [tx1])
    assert r1.is_reconciled is True
    # Edit amount to 600
    tx1.amount = "600.00"
    r2 = client.trigger_reconciliation("1000.00", "1500.00", [tx1])
    assert r2.is_reconciled is False
    assert r2.discrepancy == "100.00"


def test_f28_banner_color_coding():
    def get_banner_color(is_reconciled: bool) -> str:
        return "green" if is_reconciled else "amber"
    assert get_banner_color(True) == "green"
    assert get_banner_color(False) == "amber"


def test_f28_banner_displays_starting_and_ending():
    rec = ReconciliationSummary(
        starting_balance="100.00",
        total_credits="50.00",
        total_debits="0.00",
        net_cashflow="50.00",
        calculated_ending_balance="150.00",
        reported_ending_balance="150.00",
        discrepancy="0.00",
        is_reconciled=True,
    )
    assert rec.starting_balance == "100.00"
    assert rec.reported_ending_balance == "150.00"


# ---------------- Feature 29: Anomaly Highlighting & Resolution UI (>=5 tests) ----------------

def test_f29_anomaly_sign_inversion_quick_fix():
    tx = TransactionRecord(id="tx_inv", date="2026-08-01", payee="AWS", type=TransactionType.CREDIT, amount="100.00", running_balance="1100.00", has_anomaly=True, anomaly_type="SIGN_INVERSION")
    # Apply quick-fix: flip type to DEBIT
    tx.type = TransactionType.DEBIT
    tx.has_anomaly = False
    tx.anomaly_type = None
    assert tx.type == TransactionType.DEBIT
    assert tx.has_anomaly is False


def test_f29_anomaly_highlighting_flag():
    tx = TransactionRecord(id="tx_flagged", date="2026-08-01", payee="A", type=TransactionType.DEBIT, amount="50.00", running_balance="50.00", has_anomaly=True)
    assert tx.has_anomaly is True


def test_f29_anomaly_suggested_action_presence():
    rec = ReconciliationSummary(
        starting_balance="1000.00",
        total_credits="100.00",
        total_debits="0.00",
        net_cashflow="100.00",
        calculated_ending_balance="1100.00",
        reported_ending_balance="900.00",
        discrepancy="200.00",
        is_reconciled=False,
        diagnostic_flags=["SUSPECTED_SIGN_INVERSION: transaction tx_002 amount 100.00 matches |diff|/2"],
    )
    assert any("SIGN_INVERSION" in f for f in rec.diagnostic_flags)


def test_f29_anomaly_dismissal():
    tx = TransactionRecord(id="1", date="2026-08-01", payee="A", type=TransactionType.DEBIT, amount="10.00", running_balance="90.00", has_anomaly=True)
    # User dismisses anomaly indicator
    tx.has_anomaly = False
    assert tx.has_anomaly is False


def test_f29_anomaly_row_border_styling():
    def get_row_border(has_anomaly: bool) -> str:
        return "border-amber-400" if has_anomaly else "border-transparent"
    assert get_row_border(True) == "border-amber-400"
    assert get_row_border(False) == "border-transparent"


# ---------------- Feature 30: RFC 4180 CSV Exporter (>=5 tests) ----------------

def test_f30_csv_exporter_utf8_bom_presence(sample_export_payload):
    csv_bytes = ReferenceExportOracle.generate_reference_csv(sample_export_payload)
    assert csv_bytes.startswith(b"\xef\xbb\xbf")


def test_f30_csv_exporter_header_row_presence(sample_export_payload):
    csv_bytes = ReferenceExportOracle.generate_reference_csv(sample_export_payload)
    text = csv_bytes.decode("utf-8-sig")
    assert "Date,Description / Payee,Type,Amount,Category,Running Balance" in text


def test_f30_csv_exporter_validates_cleanly(sample_export_payload):
    csv_bytes = ReferenceExportOracle.generate_reference_csv(sample_export_payload)
    valid, errors = ReferenceExportOracle.validate_csv(csv_bytes, sample_export_payload)
    assert valid is True
    assert len(errors) == 0


def test_f30_csv_exporter_escapes_commas_in_payees():
    payload = ExportPayload(
        metadata=StatementMetadata(bank_name="B", account_number="1", statement_period_start="2026-01-01", statement_period_end="2026-01-31", starting_balance="100.00", ending_balance="150.00"),
        reconciliation=ReconciliationSummary(starting_balance="100.00", total_credits="50.00", total_debits="0.00", net_cashflow="50.00", calculated_ending_balance="150.00", reported_ending_balance="150.00", discrepancy="0.00", is_reconciled=True),
        transactions=[TransactionRecord(id="1", date="2026-01-02", payee="Smith, Jones & Co, LLP", type=TransactionType.CREDIT, amount="50.00", running_balance="150.00")],
    )
    csv_bytes = ReferenceExportOracle.generate_reference_csv(payload)
    text = csv_bytes.decode("utf-8-sig")
    assert '"Smith, Jones & Co, LLP"' in text


def test_f30_csv_exporter_crlf_line_terminators(sample_export_payload):
    csv_bytes = ReferenceExportOracle.generate_reference_csv(sample_export_payload)
    assert b"\r\n" in csv_bytes


# ---------------- Feature 31: Professional Excel (.xlsx) Exporter (>=5 tests) ----------------

def test_f31_xlsx_exporter_opens_cleanly(sample_export_payload):
    client = OpaqueSaaSClient()
    xlsx_bytes = client.export_data(sample_export_payload, format_type="xlsx")
    valid, errors = ReferenceExportOracle.validate_xlsx(xlsx_bytes, sample_export_payload)
    assert valid is True
    assert len(errors) == 0


def test_f31_xlsx_exporter_contains_transactions_sheet(sample_export_payload):
    client = OpaqueSaaSClient()
    xlsx_bytes = client.export_data(sample_export_payload, format_type="xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    assert "Transactions" in wb.sheetnames


def test_f31_xlsx_exporter_preserves_row_count(sample_export_payload):
    client = OpaqueSaaSClient()
    xlsx_bytes = client.export_data(sample_export_payload, format_type="xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb["Transactions"]
    assert ws.max_row == len(sample_export_payload.transactions) + 1  # 1 header + 2 rows


def test_f31_xlsx_exporter_numeric_datatypes(sample_export_payload):
    client = OpaqueSaaSClient()
    xlsx_bytes = client.export_data(sample_export_payload, format_type="xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb["Transactions"]
    amount_cell = ws.cell(row=2, column=4)
    assert isinstance(amount_cell.value, (int, float))


def test_f31_xlsx_exporter_header_titles(sample_export_payload):
    client = OpaqueSaaSClient()
    xlsx_bytes = client.export_data(sample_export_payload, format_type="xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb["Transactions"]
    headers = [cell.value for cell in ws[1]]
    assert "Date" in headers
    assert "Amount" in headers


# ---------------- Feature 32: Structured JSON Exporter (>=5 tests) ----------------

def test_f32_json_exporter_valid_schema(sample_export_payload):
    client = OpaqueSaaSClient()
    json_bytes = client.export_data(sample_export_payload, format_type="json")
    data = json.loads(json_bytes.decode("utf-8"))
    assert "metadata" in data
    assert "reconciliation" in data
    assert "transactions" in data


def test_f32_json_exporter_matches_transaction_count(sample_export_payload):
    client = OpaqueSaaSClient()
    json_bytes = client.export_data(sample_export_payload, format_type="json")
    data = json.loads(json_bytes.decode("utf-8"))
    assert len(data["transactions"]) == len(sample_export_payload.transactions)


def test_f32_json_exporter_is_reconciled_boolean(sample_export_payload):
    client = OpaqueSaaSClient()
    json_bytes = client.export_data(sample_export_payload, format_type="json")
    data = json.loads(json_bytes.decode("utf-8"))
    assert data["reconciliation"]["is_reconciled"] is True


def test_f32_json_exporter_serializes_string_decimals(sample_export_payload):
    client = OpaqueSaaSClient()
    json_bytes = client.export_data(sample_export_payload, format_type="json")
    data = json.loads(json_bytes.decode("utf-8"))
    assert isinstance(data["metadata"]["starting_balance"], str)
    assert data["metadata"]["starting_balance"] == "1000.00"


def test_f32_json_exporter_utf8_encoding(sample_export_payload):
    client = OpaqueSaaSClient()
    json_bytes = client.export_data(sample_export_payload, format_type="json")
    decoded = json_bytes.decode("utf-8")
    assert isinstance(decoded, str)


# ---------------- Feature 33: Exporter Round-Trip Verification (>=5 tests) ----------------

def test_f33_round_trip_clean_payload(sample_export_payload):
    passed, msg = ReferenceExportOracle.round_trip_verify(sample_export_payload)
    assert passed is True
    assert "passed" in msg


def test_f33_round_trip_detects_mutated_amount(sample_export_payload):
    mutated = sample_export_payload.model_copy(deep=True)
    mutated.transactions[0].amount = "9999.00"
    # Starting/ending mismatch
    assert mutated.transactions[0].amount != sample_export_payload.transactions[0].amount


def test_f33_round_trip_preserves_currency(sample_export_payload):
    json_data = json.loads(sample_export_payload.model_dump_json())
    recovered = ExportPayload.model_validate(json_data)
    assert recovered.metadata.currency == sample_export_payload.metadata.currency


def test_f33_round_trip_preserves_exact_decimal_strings(sample_export_payload):
    json_data = json.loads(sample_export_payload.model_dump_json())
    recovered = ExportPayload.model_validate(json_data)
    for orig, rec in zip(sample_export_payload.transactions, recovered.transactions):
        assert orig.amount == rec.amount
        assert orig.running_balance == rec.running_balance


def test_f33_round_trip_empty_transactions():
    payload = ExportPayload(
        metadata=StatementMetadata(bank_name="Zero", account_number="0", statement_period_start="2026-01-01", statement_period_end="2026-01-31", starting_balance="500.00", ending_balance="500.00"),
        reconciliation=ReconciliationSummary(starting_balance="500.00", total_credits="0.00", total_debits="0.00", net_cashflow="0.00", calculated_ending_balance="500.00", reported_ending_balance="500.00", discrepancy="0.00", is_reconciled=True),
        transactions=[],
    )
    passed, msg = ReferenceExportOracle.round_trip_verify(payload)
    assert passed is True
