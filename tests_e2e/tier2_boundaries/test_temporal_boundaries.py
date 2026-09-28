"""
Tier 2: Boundary & Corner Cases — Temporal & Calendar Date Boundaries.
Verifies:
- Leap year dates (Feb 29 on leap years: 2024, 2028)
- Month-end rollover transitions (Jan 31 -> Feb 01)
- Year-end boundary transitions (Dec 31 -> Jan 01)
- Multiple same-day transactions (5 on same date)
- Chronological sequence detection
"""
from datetime import date
from decimal import Decimal
import pytest

from tests_e2e.harness.contracts import (
    TransactionRecord,
    TransactionType,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle


def test_b_temporal_leap_year_february_29():
    leap_date = date.fromisoformat("2028-02-29")
    assert leap_date.year == 2028
    assert leap_date.month == 2
    assert leap_date.day == 29

    tx = TransactionRecord(
        id="tx_leap",
        date="2028-02-29",
        payee="Leap Day Bonus",
        type=TransactionType.CREDIT,
        amount="1000.00",
        running_balance="2000.00",
    )
    rec = ReferenceReconciliationOracle.compute_reconciliation(Decimal("1000.00"), Decimal("2000.00"), [tx])
    assert rec.is_reconciled is True


def test_b_temporal_month_end_rollover():
    tx1 = TransactionRecord(id="1", date="2026-01-31", payee="Jan Last", type=TransactionType.CREDIT, amount="100.00", running_balance="1100.00")
    tx2 = TransactionRecord(id="2", date="2026-02-01", payee="Feb First", type=TransactionType.DEBIT, amount="50.00", running_balance="1050.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(Decimal("1000.00"), Decimal("1050.00"), [tx1, tx2])
    assert rec.is_reconciled is True
    assert not any("DATE_OUT_OF_SEQUENCE" in f for f in rec.diagnostic_flags)


def test_b_temporal_year_end_rollover():
    tx1 = TransactionRecord(id="1", date="2025-12-31", payee="New Year Eve Dinner", type=TransactionType.DEBIT, amount="200.00", running_balance="800.00")
    tx2 = TransactionRecord(id="2", date="2026-01-01", payee="New Year Day Deposit", type=TransactionType.CREDIT, amount="500.00", running_balance="1300.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(Decimal("1000.00"), Decimal("1300.00"), [tx1, tx2])
    assert rec.is_reconciled is True
    assert not any("DATE_OUT_OF_SEQUENCE" in f for f in rec.diagnostic_flags)


def test_b_temporal_multiple_transactions_same_day():
    # 5 transactions on the exact same date
    txs = [
        TransactionRecord(id=f"tx_{i}", date="2026-08-15", payee=f"Merchant {i}", type=TransactionType.DEBIT, amount="10.00", running_balance=f"{1000 - i*10}.00")
        for i in range(1, 6)
    ]
    rec = ReferenceReconciliationOracle.compute_reconciliation(Decimal("1000.00"), Decimal("950.00"), txs)
    assert rec.is_reconciled is True
    assert not any("DATE_OUT_OF_SEQUENCE" in f for f in rec.diagnostic_flags)


def test_b_temporal_chronological_violation_flagging():
    tx1 = TransactionRecord(id="1", date="2026-08-20", payee="Late August", type=TransactionType.CREDIT, amount="50.00", running_balance="1050.00")
    tx2 = TransactionRecord(id="2", date="2026-08-10", payee="Early August", type=TransactionType.CREDIT, amount="50.00", running_balance="1100.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(Decimal("1000.00"), Decimal("1100.00"), [tx1, tx2])
    assert any("DATE_OUT_OF_SEQUENCE" in f for f in rec.diagnostic_flags)
