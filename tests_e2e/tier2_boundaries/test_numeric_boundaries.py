"""
Tier 2: Boundary & Corner Cases — Numeric & Currency Precision Boundaries.
Verifies:
- Zero amount transactions ($0.00$)
- Cents precision / rounding ($0.01$, $0.99$)
- Extreme large values ($100,000,000,000.00$)
- Floating-point drift resistance ($0.1 + 0.2 == 0.3$, $1.00 - 0.90 == 0.10$)
- Negative net cashflow exceeding starting balance
"""
from decimal import Decimal
import pytest

from tests_e2e.harness.contracts import (
    TransactionRecord,
    TransactionType,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle


def test_b_numeric_zero_dollar_transaction():
    start = Decimal("1000.00")
    tx = TransactionRecord(
        id="tx_zero",
        date="2026-08-01",
        payee="Waived Account Fee",
        type=TransactionType.DEBIT,
        amount="0.00",
        running_balance="1000.00",
    )
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("1000.00"), [tx])
    assert rec.is_reconciled is True
    assert rec.total_debits == "0.00"
    assert rec.net_cashflow == "0.00"


def test_b_numeric_penny_precision():
    start = Decimal("0.00")
    # Add 1 cent and 99 cents
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="Penny", type=TransactionType.CREDIT, amount="0.01", running_balance="0.01")
    tx2 = TransactionRecord(id="2", date="2026-08-02", payee="99 Cents", type=TransactionType.CREDIT, amount="0.99", running_balance="1.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("1.00"), [tx1, tx2])
    assert rec.is_reconciled is True
    assert rec.total_credits == "1.00"
    assert rec.calculated_ending_balance == "1.00"


def test_b_numeric_extreme_treasury_magnitudes():
    start = Decimal("50000000000.00")  # 50 Billion
    deposit = Decimal("25000000000.50")
    withdrawal = Decimal("12500000000.25")
    expected_end = Decimal("62500000000.25")

    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="Gov Bond", type=TransactionType.CREDIT, amount=str(deposit), running_balance="75000000000.50")
    tx2 = TransactionRecord(id="2", date="2026-08-02", payee="Syndicate", type=TransactionType.DEBIT, amount=str(withdrawal), running_balance=str(expected_end))

    rec = ReferenceReconciliationOracle.compute_reconciliation(start, expected_end, [tx1, tx2])
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == "62500000000.25"
    assert rec.discrepancy == "0.00"


def test_b_numeric_floating_point_drift_resistance():
    # Demonstrates float failure: 0.1 + 0.2 != 0.3 in IEEE 754, but Decimal must be exactly 0.30
    flt_sum = 0.1 + 0.2
    assert flt_sum != 0.3  # IEEE 754 float failure

    start = Decimal("0.00")
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="P1", type=TransactionType.CREDIT, amount="0.10", running_balance="0.10")
    tx2 = TransactionRecord(id="2", date="2026-08-02", payee="P2", type=TransactionType.CREDIT, amount="0.20", running_balance="0.30")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("0.30"), [tx1, tx2])
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == "0.30"


def test_b_numeric_sub_penny_quantization():
    # Any fractional cent must round half up to 2 decimal places
    d1 = to_decimal("124.505")
    assert d1 == Decimal("124.51")
    d2 = to_decimal("124.504")
    assert d2 == Decimal("124.50")


def test_b_numeric_negative_cashflow_exceeding_starting_balance():
    start = Decimal("100.00")
    tx = TransactionRecord(id="1", date="2026-08-01", payee="Overdraw", type=TransactionType.DEBIT, amount="350.00", running_balance="-250.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("-250.00"), [tx])
    assert rec.is_reconciled is True
    assert rec.net_cashflow == "-350.00"
    assert rec.calculated_ending_balance == "-250.00"
