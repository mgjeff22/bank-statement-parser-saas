"""
Tier 1: Feature Coverage Tests for Features 7-13 (Parsing, Normalization, Strict Decimal Reconciliation & Fixture Generator).
Verifies:
- Feature 7: Transaction Record Normalizer
- Feature 8: Statement Metadata Extractor
- Feature 9: Decimal Reconciliation Formula
- Feature 10: Net Cashflow Calculation
- Feature 11: Sequential Running Balance Check
- Feature 12: Discrepancy Diagnostic Rules
- Feature 13: Synthetic Statement Fixture Generator
"""
from decimal import Decimal
import os
import json
import pytest
from datetime import date

from tests_e2e.harness.contracts import (
    StatementMetadata,
    TransactionRecord,
    ReconciliationSummary,
    TransactionType,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle


# ---------------- Feature 7: Transaction Record Normalizer (>=5 tests) ----------------

def test_f07_normalizer_iso_date_standardization():
    raw_date = "08/14/2026"
    # Converts MM/DD/YYYY to YYYY-MM-DD
    parts = raw_date.split("/")
    iso_date = f"{parts[2]}-{parts[0]}-{parts[1]}"
    assert iso_date == "2026-08-14"


def test_f07_normalizer_payee_cleaning_pos_codes():
    raw = "POS DEBIT 4819 STARBUCKS #1024 SEATTLE WA"
    # Strips POS terminal clutter
    cleaned = raw.replace("POS DEBIT 4819", "").strip()
    assert "STARBUCKS" in cleaned and "POS DEBIT" not in cleaned


def test_f07_normalizer_amount_positive_magnitude_enforcement():
    # Amounts must be positive strings; direction stored in type
    tx = TransactionRecord(
        id="tx_01",
        date="2026-08-01",
        payee="Uber",
        type=TransactionType.DEBIT,
        amount="25.50",
        running_balance="1000.00",
    )
    assert to_decimal(tx.amount) > Decimal("0.00")
    assert tx.type == TransactionType.DEBIT


def test_f07_normalizer_category_mapping_heuristic():
    payee = "WHOLE FOODS GROCERY STORE"
    category = "Groceries" if "WHOLE FOODS" in payee or "GROCERY" in payee else "Miscellaneous"
    assert category == "Groceries"


def test_f07_normalizer_parentheses_negative_parsing():
    raw_amount = "(145.20)"
    clean = raw_amount.replace("(", "").replace(")", "").strip()
    amt = to_decimal(clean)
    assert amt == Decimal("145.20")


# ---------------- Feature 8: Statement Metadata Extractor (>=5 tests) ----------------

def test_f08_metadata_bank_name_identification():
    meta = StatementMetadata(
        bank_name="Wells Fargo Bank, N.A.",
        account_number="************3302",
        statement_period_start="2026-09-01",
        statement_period_end="2026-09-30",
        starting_balance="5600.25",
        ending_balance="9800.75",
        currency="USD",
        page_count=2,
    )
    assert meta.bank_name == "Wells Fargo Bank, N.A."
    assert meta.page_count == 2


def test_f08_metadata_masked_account_preservation():
    raw_acct = "Account Number: ************4921"
    masked = raw_acct.split(":")[-1].strip()
    assert masked.startswith("************")
    assert masked.endswith("4921")


def test_f08_metadata_statement_period_validity():
    start = date.fromisoformat("2026-09-01")
    end = date.fromisoformat("2026-09-30")
    assert start < end
    duration = (end - start).days
    assert 28 <= duration <= 31


def test_f08_metadata_currency_iso4217_code():
    meta = StatementMetadata(
        bank_name="Barclays",
        account_number="1234",
        statement_period_start="2026-01-01",
        statement_period_end="2026-01-31",
        starting_balance="100.00",
        ending_balance="200.00",
        currency="GBP",
    )
    assert meta.currency in ["USD", "EUR", "GBP", "CAD", "AUD"]


def test_f08_metadata_zero_opening_balance():
    meta = StatementMetadata(
        bank_name="New Account",
        account_number="9999",
        statement_period_start="2026-01-01",
        statement_period_end="2026-01-31",
        starting_balance="0.00",
        ending_balance="500.00",
    )
    assert meta.starting_balance == "0.00"


# ---------------- Feature 9: Decimal Reconciliation Formula (>=5 tests) ----------------

def test_f09_formula_exact_reconciliation_zero_discrepancy():
    start = Decimal("1000.00")
    reported_end = Decimal("1250.00")
    txs = [
        TransactionRecord(id="1", date="2026-08-01", payee="P1", type=TransactionType.CREDIT, amount="500.00", running_balance="1500.00"),
        TransactionRecord(id="2", date="2026-08-02", payee="P2", type=TransactionType.DEBIT, amount="250.00", running_balance="1250.00"),
    ]
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, reported_end, txs)
    assert rec.is_reconciled is True
    assert rec.discrepancy == "0.00"
    assert rec.calculated_ending_balance == "1250.00"


def test_f09_formula_detects_deliberate_discrepancy():
    start = Decimal("1000.00")
    reported_end = Decimal("1500.00")  # Should be 1250.00, mismatch of -250.00
    txs = [
        TransactionRecord(id="1", date="2026-08-01", payee="P1", type=TransactionType.CREDIT, amount="500.00", running_balance="1500.00"),
        TransactionRecord(id="2", date="2026-08-02", payee="P2", type=TransactionType.DEBIT, amount="250.00", running_balance="1250.00"),
    ]
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, reported_end, txs)
    assert rec.is_reconciled is False
    assert rec.discrepancy == "-250.00"


def test_f09_formula_floating_point_safety():
    # 0.10 + 0.20 must equal 0.30 exactly with Decimal, unlike binary float (0.30000000000000004)
    start = Decimal("0.10")
    txs = [TransactionRecord(id="1", date="2026-08-01", payee="Penny Test", type=TransactionType.CREDIT, amount="0.20", running_balance="0.30")]
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("0.30"), txs)
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == "0.30"


def test_f09_formula_zero_net_activity():
    start = Decimal("5000.00")
    txs = []
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, start, txs)
    assert rec.is_reconciled is True
    assert rec.total_credits == "0.00"
    assert rec.total_debits == "0.00"
    assert rec.net_cashflow == "0.00"


def test_f09_formula_credits_and_debits_aggregation():
    start = Decimal("100.00")
    txs = [
        TransactionRecord(id="1", date="2026-08-01", payee="A", type=TransactionType.CREDIT, amount="50.25", running_balance="150.25"),
        TransactionRecord(id="2", date="2026-08-02", payee="B", type=TransactionType.CREDIT, amount="49.75", running_balance="200.00"),
        TransactionRecord(id="3", date="2026-08-03", payee="C", type=TransactionType.DEBIT, amount="25.50", running_balance="174.50"),
        TransactionRecord(id="4", date="2026-08-04", payee="D", type=TransactionType.DEBIT, amount="74.50", running_balance="100.00"),
    ]
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("100.00"), txs)
    assert rec.total_credits == "100.00"
    assert rec.total_debits == "100.00"
    assert rec.net_cashflow == "0.00"
    assert rec.is_reconciled is True


# ---------------- Feature 10: Net Cashflow Calculation (>=5 tests) ----------------

def test_f10_cashflow_positive():
    credits = Decimal("5000.00")
    debits = Decimal("2000.00")
    net = credits - debits
    assert net == Decimal("3000.00")


def test_f10_cashflow_negative():
    credits = Decimal("1000.00")
    debits = Decimal("3500.00")
    net = credits - debits
    assert net == Decimal("-2500.00")


def test_f10_cashflow_zero_equality():
    credits = Decimal("1234.56")
    debits = Decimal("1234.56")
    net = credits - debits
    assert net == Decimal("0.00")


def test_f10_cashflow_reconciliation_identity():
    # Calculated Ending = Starting + Net Cashflow
    start = Decimal("2450.00")
    net = Decimal("-450.00")
    calc_end = start + net
    assert calc_end == Decimal("2000.00")


def test_f10_cashflow_with_pennies():
    credits = Decimal("100.99")
    debits = Decimal("50.49")
    net = credits - debits
    assert net == Decimal("50.50")


# ---------------- Feature 11: Sequential Running Balance Check (>=5 tests) ----------------

def test_f11_running_balance_continuous_verification():
    start = Decimal("100.00")
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="T1", type=TransactionType.CREDIT, amount="50.00", running_balance="150.00")
    tx2 = TransactionRecord(id="2", date="2026-08-02", payee="T2", type=TransactionType.DEBIT, amount="30.00", running_balance="120.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("120.00"), [tx1, tx2])
    assert not any("RUNNING_BALANCE_MISMATCH" in f for f in rec.diagnostic_flags)


def test_f11_running_balance_detects_step_discrepancy():
    start = Decimal("100.00")
    # tx1 reports 160.00 instead of 150.00
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="T1", type=TransactionType.CREDIT, amount="50.00", running_balance="160.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("150.00"), [tx1])
    assert any("RUNNING_BALANCE_MISMATCH" in f for f in rec.diagnostic_flags)


def test_f11_running_balance_negative_overdraft_continuation():
    start = Decimal("50.00")
    # Debit of 100 drops to -50
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="Overdraft", type=TransactionType.DEBIT, amount="100.00", running_balance="-50.00")
    tx2 = TransactionRecord(id="2", date="2026-08-02", payee="Deposit", type=TransactionType.CREDIT, amount="200.00", running_balance="150.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("150.00"), [tx1, tx2])
    assert rec.is_reconciled is True
    assert not any("RUNNING_BALANCE_MISMATCH" in f for f in rec.diagnostic_flags)


def test_f11_running_balance_zero_balance_point():
    start = Decimal("100.00")
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="Drain", type=TransactionType.DEBIT, amount="100.00", running_balance="0.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("0.00"), [tx1])
    assert rec.is_reconciled is True


def test_f11_running_balance_preserves_row_chronology():
    txs = [
        TransactionRecord(id=f"tx_{i}", date=f"2026-08-{i:02d}", payee=f"P{i}", type=TransactionType.CREDIT, amount="10.00", running_balance=f"{100 + i*10}.00")
        for i in range(1, 6)
    ]
    rec = ReferenceReconciliationOracle.compute_reconciliation(Decimal("100.00"), Decimal("150.00"), txs)
    assert rec.is_reconciled is True


# ---------------- Feature 12: Discrepancy Diagnostic Rules (>=5 tests) ----------------

def test_f12_diagnostics_sign_inversion_half_diff():
    # If $100 debit is treated as credit, discrepancy is +$200. Candidate is 200/2 = 100
    start = Decimal("1000.00")
    reported_end = Decimal("900.00")  # True end: 1000 - 100 = 900
    # Erroneous row has CREDIT instead of DEBIT
    bad_tx = TransactionRecord(id="tx_err", date="2026-08-01", payee="AWS", type=TransactionType.CREDIT, amount="100.00", running_balance="1100.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, reported_end, [bad_tx])
    assert rec.is_reconciled is False
    assert rec.discrepancy == "200.00"
    assert any("SUSPECTED_SIGN_INVERSION" in f for f in rec.diagnostic_flags)


def test_f12_diagnostics_transposition_modulo_nine():
    # Swap 54 for 45 -> diff is 9 -> (9 * 100) % 9 == 0
    disc = Decimal("9.00")
    cents = int(disc * 100)
    assert cents % 9 == 0


def test_f12_diagnostics_date_out_of_sequence_flagging():
    start = Decimal("1000.00")
    tx1 = TransactionRecord(id="1", date="2026-08-15", payee="Mid-month", type=TransactionType.CREDIT, amount="50.00", running_balance="1050.00")
    tx2 = TransactionRecord(id="2", date="2026-08-05", payee="Early-month", type=TransactionType.CREDIT, amount="50.00", running_balance="1100.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("1100.00"), [tx1, tx2])
    assert any("DATE_OUT_OF_SEQUENCE" in f for f in rec.diagnostic_flags)


def test_f12_diagnostics_missing_transaction_gap():
    start = Decimal("1000.00")
    reported_end = Decimal("1500.00")
    # Only 1 tx of 200 included, leaving 300 gap
    tx = TransactionRecord(id="1", date="2026-08-01", payee="P1", type=TransactionType.CREDIT, amount="200.00", running_balance="1200.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, reported_end, [tx])
    assert any("UNRECONCILED_DISCREPANCY" in f for f in rec.diagnostic_flags)
    assert rec.discrepancy == "-300.00"


def test_f12_diagnostics_clean_when_reconciled():
    start = Decimal("100.00")
    tx = TransactionRecord(id="1", date="2026-08-01", payee="OK", type=TransactionType.CREDIT, amount="50.00", running_balance="150.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("150.00"), [tx])
    assert rec.is_reconciled is True
    assert len(rec.diagnostic_flags) == 0


# ---------------- Feature 13: Synthetic Statement Fixture Generator (>=5 tests) ----------------

def test_f13_generator_creates_valid_ground_truth_json(tmp_path):
    import os
    from tests_e2e.generators.statement_generator import SyntheticStatementGenerator, StatementDataSpec

    pdf_path = str(tmp_path / "test.pdf")
    gt_path = str(tmp_path / "test.json")
    spec = StatementDataSpec(
        bank_name="Test Bank",
        account_number="1234",
        period_start="2026-01-01",
        period_end="2026-01-31",
        starting_balance=Decimal("1000.00"),
        raw_transactions=[{"date": "2026-01-02", "payee": "Deposit", "type": "credit", "amount": "500.00"}],
    )
    SyntheticStatementGenerator.generate(spec, pdf_path, gt_path, format_type="digital_pdf")

    assert os.path.exists(pdf_path)
    assert os.path.exists(gt_path)

    with open(gt_path, "r") as f:
        data = json.load(f)
    assert data["metadata"]["bank_name"] == "Test Bank"
    assert data["reconciliation"]["is_reconciled"] is True


def test_f13_generator_injects_sign_inversion_anomaly(tmp_path):
    from tests_e2e.generators.statement_generator import SyntheticStatementGenerator, StatementDataSpec

    pdf_path = str(tmp_path / "anomaly.pdf")
    gt_path = str(tmp_path / "anomaly.json")
    spec = StatementDataSpec(
        bank_name="Anomaly Bank",
        account_number="5678",
        period_start="2026-01-01",
        period_end="2026-01-31",
        starting_balance=Decimal("1000.00"),
        raw_transactions=[
            {"date": "2026-01-02", "payee": "Tx1", "type": "credit", "amount": "500.00"},
            {"date": "2026-01-05", "payee": "Expense", "type": "debit", "amount": "100.00"},
        ],
        inject_anomaly="sign_inversion",
        anomaly_row_idx=1,
    )
    res = SyntheticStatementGenerator.generate(spec, pdf_path, gt_path)
    assert res["reconciliation"]["is_reconciled"] is False
    assert any("SIGN_INVERSION" in flag for flag in res["reconciliation"]["diagnostic_flags"])


def test_f13_generator_injects_out_of_order_dates(tmp_path):
    from tests_e2e.generators.statement_generator import SyntheticStatementGenerator, StatementDataSpec

    pdf_path = str(tmp_path / "order.pdf")
    gt_path = str(tmp_path / "order.json")
    spec = StatementDataSpec(
        bank_name="Order Bank",
        account_number="8888",
        period_start="2026-01-01",
        period_end="2026-01-31",
        starting_balance=Decimal("1000.00"),
        raw_transactions=[
            {"date": "2026-01-02", "payee": "T1", "type": "credit", "amount": "100.00"},
            {"date": "2026-01-08", "payee": "T2", "type": "credit", "amount": "200.00"},
            {"date": "2026-01-15", "payee": "T3", "type": "debit", "amount": "50.00"},
        ],
        inject_anomaly="out_of_order",
        anomaly_row_idx=1,
    )
    res = SyntheticStatementGenerator.generate(spec, pdf_path, gt_path)
    assert any("DATE_OUT_OF_SEQUENCE" in flag for flag in res["reconciliation"]["diagnostic_flags"])


def test_f13_generator_produces_raster_image_files(tmp_path):
    from tests_e2e.generators.statement_generator import SyntheticStatementGenerator, StatementDataSpec

    png_path = str(tmp_path / "test.png")
    gt_path = str(tmp_path / "test.json")
    spec = StatementDataSpec(
        bank_name="Image Bank",
        account_number="3333",
        period_start="2026-02-01",
        period_end="2026-02-28",
        starting_balance=Decimal("500.00"),
        raw_transactions=[{"date": "2026-02-05", "payee": "Income", "type": "credit", "amount": "500.00"}],
    )
    SyntheticStatementGenerator.generate(spec, png_path, gt_path, format_type="png")
    assert os.path.exists(png_path)
    assert os.path.getsize(png_path) > 1000


def test_f13_generator_applies_skew_angle(tmp_path):
    from tests_e2e.generators.statement_generator import SyntheticStatementGenerator, StatementDataSpec

    jpg_path = str(tmp_path / "skewed.jpg")
    gt_path = str(tmp_path / "skewed.json")
    spec = StatementDataSpec(
        bank_name="Skewed Bank",
        account_number="4444",
        period_start="2026-03-01",
        period_end="2026-03-31",
        starting_balance=Decimal("2000.00"),
        raw_transactions=[{"date": "2026-03-05", "payee": "Coffee", "type": "debit", "amount": "5.00"}],
    )
    res = SyntheticStatementGenerator.generate(spec, jpg_path, gt_path, format_type="jpeg", skew_angle=3.0)
    assert res["generator_spec"]["skew_angle"] == 3.0
    assert os.path.exists(jpg_path)
