"""
Tier 2: Boundary & Corner Cases — Balance & Overdraft Boundaries.
Verifies:
- Starting balance of exactly zero ($0.00$)
- Negative starting balance (overdraft carry-forward)
- Mid-period overdraft dipping negative and recovering positive
- Ending balance remaining in overdraft
- Starting balance equal to ending balance with high volume turnover
"""
from decimal import Decimal
import pytest

from tests_e2e.harness.contracts import (
    TransactionRecord,
    TransactionType,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle


def test_b_balance_zero_starting_balance():
    start = Decimal("0.00")
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="Initial Deposit", type=TransactionType.CREDIT, amount="100.00", running_balance="100.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("100.00"), [tx1])
    assert rec.is_reconciled is True
    assert rec.starting_balance == "0.00"


def test_b_balance_negative_starting_balance():
    # Account starts with negative $150.00
    start = Decimal("-150.00")
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="Catch-up Deposit", type=TransactionType.CREDIT, amount="300.00", running_balance="150.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("150.00"), [tx1])
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == "150.00"


def test_b_balance_mid_period_overdraft_recovery():
    # Starts at 50, drops to -50, recovers to 150
    start = Decimal("50.00")
    tx1 = TransactionRecord(id="1", date="2026-08-02", payee="Large Bill", type=TransactionType.DEBIT, amount="100.00", running_balance="-50.00")
    tx2 = TransactionRecord(id="2", date="2026-08-03", payee="Fee", type=TransactionType.DEBIT, amount="35.00", running_balance="-85.00")
    tx3 = TransactionRecord(id="3", date="2026-08-05", payee="Paycheck", type=TransactionType.CREDIT, amount="500.00", running_balance="415.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("415.00"), [tx1, tx2, tx3])
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == "415.00"


def test_b_balance_unresolved_ending_overdraft():
    start = Decimal("100.00")
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="Huge Expense", type=TransactionType.DEBIT, amount="350.00", running_balance="-250.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("-250.00"), [tx1])
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == "-250.00"


def test_b_balance_equal_start_end_with_high_turnover():
    start = Decimal("5000.00")
    tx1 = TransactionRecord(id="1", date="2026-08-01", payee="Inflow", type=TransactionType.CREDIT, amount="25000.00", running_balance="30000.00")
    tx2 = TransactionRecord(id="2", date="2026-08-02", payee="Outflow", type=TransactionType.DEBIT, amount="25000.00", running_balance="5000.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, start, [tx1, tx2])
    assert rec.is_reconciled is True
    assert rec.total_credits == "25000.00"
    assert rec.total_debits == "25000.00"
    assert rec.net_cashflow == "0.00"
