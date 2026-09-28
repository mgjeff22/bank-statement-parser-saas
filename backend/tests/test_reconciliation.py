"""
Unit and Integration Tests for Strict Decimal Mathematical Reconciliation Engine.

Verifies:
1. Zero floating-point drift (Decimal precision, ROUND_HALF_UP)
2. Formula: Starting Balance + Total Credits - Total Debits == Ending Balance
3. Net Cashflow: Total Credits - Total Debits
4. Sequential running balance verification
5. Missing Transaction Gap detection
6. Sign Inversion anomaly detection (|Discrepancy| / 2 match)
7. Digit Transposition check (Modulo 9 rule)
8. Out-of-Order Date sequence detection
9. Overdraft / Negative balance handling
10. Empty transactions edge case
"""
from decimal import Decimal
import pytest

from app.schemas.transaction import TransactionRecord
from app.services.reconciliation import (
    reconcile_statement,
    to_decimal,
    format_decimal,
)


def make_tx(
    tx_id: str,
    date: str,
    payee: str,
    tx_type: str,
    amount: str,
    running_balance: str = "0.00",
    category: str = "Miscellaneous",
) -> TransactionRecord:
    return TransactionRecord(
        id=tx_id,
        date=date,
        payee=payee,
        type=tx_type,
        amount=amount,
        running_balance=running_balance,
        category=category,
        has_anomaly=False,
        anomaly_type=None,
    )


class TestReconciliationMath:
    def test_zero_floating_point_drift(self):
        """Verifies that 0.10 + 0.20 equals exactly 0.30 with zero float drift."""
        # Standard float drift in Python: 0.1 + 0.2 == 0.30000000000000004
        d1 = to_decimal("0.10")
        d2 = to_decimal("0.20")
        assert (d1 + d2) == Decimal("0.30")
        assert format_decimal(d1 + d2) == "0.30"

    def test_perfectly_reconciled_statement(self):
        """Tests standard reconciled statement with debits and credits."""
        txs = [
            make_tx("tx1", "2026-09-01", "Acme Payroll", "credit", "3000.00", "5500.00"),
            make_tx("tx2", "2026-09-05", "Whole Foods", "debit", "150.50", "5349.50"),
            make_tx("tx3", "2026-09-10", "Pacific Gas & Electric", "debit", "85.25", "5264.25"),
            make_tx("tx4", "2026-09-15", "Consulting Inflow", "credit", "1200.00", "6464.25"),
        ]

        summary, updated_txs = reconcile_statement(
            starting_balance="2500.00",
            ending_balance="6464.25",
            transactions=txs,
        )

        assert summary.is_reconciled is True
        assert summary.starting_balance == "2500.00"
        assert summary.total_credits == "4200.00"
        assert summary.total_debits == "235.75"
        assert summary.net_cashflow == "3964.25"
        assert summary.calculated_ending_balance == "6464.25"
        assert summary.reported_ending_balance == "6464.25"
        assert summary.discrepancy == "0.00"
        assert all(tx.has_anomaly is False for tx in updated_txs)

    def test_overdraft_negative_balance_handling(self):
        """Tests accounts dipping into negative balance and recovering."""
        txs = [
            make_tx("tx1", "2026-09-01", "Initial Rent", "debit", "600.00", "-100.00"),
            make_tx("tx2", "2026-09-02", "Bank Overdraft Fee", "debit", "35.00", "-135.00"),
            make_tx("tx3", "2026-09-03", "Cash Deposit", "credit", "500.00", "365.00"),
        ]

        summary, updated_txs = reconcile_statement(
            starting_balance="500.00",
            ending_balance="365.00",
            transactions=txs,
        )

        assert summary.is_reconciled is True
        assert summary.discrepancy == "0.00"
        assert summary.total_debits == "635.00"
        assert summary.total_credits == "500.00"
        assert summary.net_cashflow == "-135.00"
        assert summary.calculated_ending_balance == "365.00"

    def test_sign_inversion_detection_debit_as_credit(self):
        """
        When a $100.00 expense is erroneously marked as 'credit',
        calculated ending balance will be inflated by exactly $200.00.
        Discrepancy == +$200.00. |Discrepancy| / 2 == $100.00.
        """
        txs = [
            make_tx("tx1", "2026-09-01", "Payroll Deposit", "credit", "2000.00", "3000.00"),
            make_tx("tx2", "2026-09-05", "Office Supplies", "credit", "100.00", "3100.00"),  # Mistakenly credit!
            make_tx("tx3", "2026-09-10", "Utility Bill", "debit", "50.00", "2850.00"),
        ]
        # True ending balance if tx2 was debit: 1000 + 2000 - 100 - 50 = 2850.00
        # Calc ending balance with tx2 as credit: 1000 + 2000 + 100 - 50 = 3050.00
        # Discrepancy: 3050 - 2850 = +200.00

        summary, updated_txs = reconcile_statement(
            starting_balance="1000.00",
            ending_balance="2850.00",
            transactions=txs,
        )

        assert summary.is_reconciled is False
        assert summary.discrepancy == "200.00"
        # Verify tx2 was flagged as SIGN_INVERSION
        assert updated_txs[1].has_anomaly is True
        assert updated_txs[1].anomaly_type == "SIGN_INVERSION"
        assert any("Suspected sign inversion" in flag for flag in summary.diagnostic_flags)

    def test_sign_inversion_detection_credit_as_debit(self):
        """
        When a $250.00 deposit is erroneously marked as 'debit',
        calculated balance is deflated by $500.00. Discrepancy == -$500.00.
        """
        txs = [
            make_tx("tx1", "2026-09-01", "Refund Inflow", "debit", "250.00", "750.00"),  # Mistakenly debit!
            make_tx("tx2", "2026-09-05", "Groceries", "debit", "100.00", "650.00"),
        ]
        # True ending balance: 1000 + 250 - 100 = 1150.00
        # Calc ending balance: 1000 - 250 - 100 = 650.00
        # Discrepancy: 650 - 1150 = -500.00

        summary, updated_txs = reconcile_statement(
            starting_balance="1000.00",
            ending_balance="1150.00",
            transactions=txs,
        )

        assert summary.is_reconciled is False
        assert summary.discrepancy == "-500.00"
        assert updated_txs[0].has_anomaly is True
        assert updated_txs[0].anomaly_type == "SIGN_INVERSION"

    def test_missing_transaction_running_balance_gap(self):
        """
        Tests detection of a sudden gap in the running balance
        indicating a missing transaction between rows.
        """
        txs = [
            make_tx("tx1", "2026-09-01", "Deposit", "credit", "1000.00", "2000.00"),
            # An unparsed withdrawal of $150.25 occurred here in reality, so bank printed balance $1799.75 on next row
            make_tx("tx2", "2026-09-05", "Coffee", "debit", "50.00", "1799.75"),
        ]
        # Expected running bal after tx2: 2000 - 50 = 1950.00. Reported: 1799.75. Gap = 150.25.

        summary, updated_txs = reconcile_statement(
            starting_balance="1000.00",
            ending_balance="1799.75",
            transactions=txs,
        )

        assert summary.is_reconciled is False
        assert summary.discrepancy == "150.25"
        assert updated_txs[1].has_anomaly is True
        assert updated_txs[1].anomaly_type == "MISSING_GAP"
        assert any("Running balance mismatch" in flag for flag in summary.diagnostic_flags)
        assert any("gap of 150.25" in flag for flag in summary.diagnostic_flags)

    def test_out_of_order_date_detection(self):
        """Tests that backwards date sequences are flagged."""
        txs = [
            make_tx("tx1", "2026-09-15", "Item A", "debit", "50.00", "950.00"),
            make_tx("tx2", "2026-09-10", "Item B", "debit", "30.00", "920.00"),  # Earlier date after later!
            make_tx("tx3", "2026-09-20", "Item C", "debit", "20.00", "900.00"),
        ]

        summary, updated_txs = reconcile_statement(
            starting_balance="1000.00",
            ending_balance="900.00",
            transactions=txs,
        )

        assert updated_txs[1].has_anomaly is True
        assert updated_txs[1].anomaly_type == "OUT_OF_ORDER_DATE"
        assert any("Out-of-order date detected" in flag for flag in summary.diagnostic_flags)

    def test_digit_transposition_modulo_9(self):
        """
        Tests the double-entry accounting rule where transposed digits produce
        errors divisible by 9.
        E.g. $54.00 entered instead of $45.00 -> error $9.00 -> 900 % 9 == 0.
        """
        # True amount was 45.00, reported was 54.00 (diff 9.00)
        txs = [
            make_tx("tx1", "2026-09-01", "Hardware Store", "debit", "54.00", "946.00"),
        ]
        # True ending balance: 1000 - 45 = 955.00
        # Reported ending balance: 955.00
        # Calc ending balance: 1000 - 54 = 946.00
        # Discrepancy: 946 - 955 = -9.00

        summary, updated_txs = reconcile_statement(
            starting_balance="1000.00",
            ending_balance="955.00",
            transactions=txs,
        )

        assert summary.is_reconciled is False
        assert summary.discrepancy == "-9.00"
        assert any("divisible by 9" in flag for flag in summary.diagnostic_flags)
        assert updated_txs[0].has_anomaly is True
        assert updated_txs[0].anomaly_type in ["TRANSPOSITION", "MISSING_GAP"]

    def test_empty_transactions_list(self):
        """Tests statement with no transactions."""
        # Case A: Starting == Ending (Reconciled)
        summary_rec, txs_rec = reconcile_statement("500.00", "500.00", [])
        assert summary_rec.is_reconciled is True
        assert summary_rec.net_cashflow == "0.00"
        assert summary_rec.discrepancy == "0.00"

        # Case B: Starting != Ending (Unreconciled)
        summary_unrec, txs_unrec = reconcile_statement("500.00", "600.00", [])
        assert summary_unrec.is_reconciled is False
        assert summary_unrec.discrepancy == "-100.00"
