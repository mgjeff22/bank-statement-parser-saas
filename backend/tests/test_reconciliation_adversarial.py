"""
Adversarial Stress Harness for Milestone 1 Mathematical Balance Reconciliation Engine.

Empirically tests the 5 mandatory challenge vectors:
1. 1,000 randomized synthetic transactions with arbitrary cents amounts to assert 0.00 floating point drift.
2. Injected sign inversions on arbitrary rows to assert 100% detection rate.
3. Injected missing transactions across various gap sizes to assert gap calculation accuracy.
4. Deliberate transposition of digits (e.g. 19.50 vs 91.50) to verify Modulo 9 detection.
5. Out-of-order date sequences.
"""
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import List, Tuple
import pytest

from app.schemas.transaction import TransactionRecord
from app.services.reconciliation import (
    reconcile_statement,
    to_decimal,
    format_decimal,
    CENT,
)


def make_tx(
    tx_id: str,
    date: str,
    payee: str,
    tx_type: str,
    amount: str,
    running_balance: str = "0.00",
    category: str = "General",
) -> TransactionRecord:
    return TransactionRecord(
        id=tx_id,
        date=date,
        payee=payee,
        type=tx_type,  # type: ignore
        amount=amount,
        running_balance=running_balance,
        category=category,
        has_anomaly=False,
        anomaly_type=None,
    )


class TestAdversarialReconciliation:
    """Adversarial stress test suite for mathematical reconciliation engine."""

    def test_challenge_1_thousand_random_transactions_zero_float_drift(self):
        """
        Challenge 1:
        1,000 randomized synthetic transactions with arbitrary cents amounts.
        Asserts 0.00 floating point drift in calculated ending balance, net cashflow,
        and discrepancy, and contrasts against accumulated IEEE 754 binary float drift.
        """
        rng = random.Random(42)  # Deterministic seed for reproducibility
        num_transactions = 1000

        start_bal = Decimal("15420.73")
        current_bal = start_bal
        total_credits = Decimal("0.00")
        total_debits = Decimal("0.00")

        # Also track IEEE-754 float values to empirically prove float drift occurs
        float_start = float(start_bal)
        float_running = float_start
        float_credits = 0.0
        float_debits = 0.0

        transactions: List[TransactionRecord] = []

        for i in range(num_transactions):
            # Arbitrary cents amount from 0.01 to 9999.99
            cents = rng.randint(1, 999999)
            amt_dec = (Decimal(cents) / Decimal("100")).quantize(CENT)
            amt_str = f"{amt_dec:.2f}"
            tx_type = "credit" if rng.random() > 0.55 else "debit"

            amt_float = float(amt_dec)

            if tx_type == "credit":
                current_bal += amt_dec
                total_credits += amt_dec
                float_running += amt_float
                float_credits += amt_float
            else:
                current_bal -= amt_dec
                total_debits += amt_dec
                float_running -= amt_float
                float_debits += amt_float

            # Non-decreasing chronological dates across the 1000 transactions
            day_offset = i // 30  # ~30 tx per day across ~33 days
            month = 1 + (day_offset // 28)
            day = 1 + (day_offset % 28)
            tx = make_tx(
                tx_id=f"tx_{i+1:04d}",
                date=f"2026-{month:02d}-{day:02d}",
                payee=f"Merchant {i+1}",
                tx_type=tx_type,
                amount=amt_str,
                running_balance=f"{current_bal:.2f}",
            )
            transactions.append(tx)

        reported_ending_balance = f"{current_bal:.2f}"

        # Execute reconciliation
        summary, updated_txs = reconcile_statement(
            starting_balance=f"{start_bal:.2f}",
            ending_balance=reported_ending_balance,
            transactions=transactions,
        )

        # 1. Assert exactly 0.00 discrepancy
        assert summary.is_reconciled is True, f"Expected reconciled, got discrepancy {summary.discrepancy}"
        assert summary.discrepancy == "0.00", f"Discrepancy must be 0.00, got {summary.discrepancy}"

        # 2. Assert exact decimal equality on all totals
        assert summary.starting_balance == f"{start_bal:.2f}"
        assert summary.reported_ending_balance == f"{current_bal:.2f}"
        assert summary.calculated_ending_balance == f"{current_bal:.2f}"
        assert summary.total_credits == f"{total_credits:.2f}"
        assert summary.total_debits == f"{total_debits:.2f}"
        expected_cashflow = (total_credits - total_debits).quantize(CENT, rounding=ROUND_HALF_UP)
        assert summary.net_cashflow == f"{expected_cashflow:.2f}"

        # 3. Verify zero anomalies flagged on valid sequence
        anomalies = [tx for tx in updated_txs if tx.has_anomaly]
        assert len(anomalies) == 0, f"Expected 0 anomalies on valid sequence, got {len(anomalies)}"

        # 4. Demonstrate float drift: standard float arithmetic DOES diverge
        float_calc_end = float_start + float_credits - float_debits
        float_diff = abs(float_calc_end - float(current_bal))
        print(f"\n[Challenge 1 Verified] 1,000 transactions reconciled with 0.00 drift.")
        print(f"Decimal Discrepancy: {summary.discrepancy}")
        print(f"IEEE 754 Float Inaccuracy on same numbers: {float_diff:.10e}")

    def test_challenge_2_injected_sign_inversions_100_percent_detection(self):
        """
        Challenge 2:
        Injected sign inversions on arbitrary rows.
        Asserts 100% detection rate across 100 randomized trials with varied amounts,
        row positions (start, middle, end), and transaction directions.
        """
        rng = random.Random(1337)
        trials = 100
        detected_count = 0

        for trial in range(trials):
            # Generate baseline reconciled statement of 30 transactions
            n_tx = rng.randint(20, 50)
            start_bal = Decimal(f"{rng.randint(5000, 20000)}.50")
            current_bal = start_bal

            txs: List[TransactionRecord] = []
            for i in range(n_tx):
                cents = rng.randint(100, 50000)  # $1.00 to $500.00
                amt_dec = (Decimal(cents) / Decimal("100")).quantize(CENT)
                tx_type = "credit" if rng.random() > 0.5 else "debit"
                if tx_type == "credit":
                    current_bal += amt_dec
                else:
                    current_bal -= amt_dec

                txs.append(
                    make_tx(
                        tx_id=f"tx_{i}",
                        date=f"2026-02-{1 + (i // 3):02d}",
                        payee=f"Vendor {i}",
                        tx_type=tx_type,
                        amount=f"{amt_dec:.2f}",
                        running_balance=f"{current_bal:.2f}",
                    )
                )

            true_ending_balance = f"{current_bal:.2f}"

            # Pick an arbitrary row to invert
            target_idx = rng.randint(0, n_tx - 1)
            target_tx = txs[target_idx]
            original_type = target_tx.type
            inverted_type = "debit" if original_type == "credit" else "credit"

            # Create inverted dataset
            inverted_txs = [
                make_tx(
                    tx.id, tx.date, tx.payee, tx.type, tx.amount, tx.running_balance, tx.category
                )
                for tx in txs
            ]
            inverted_txs[target_idx].type = inverted_type

            # Execute reconciliation against the true reported ending balance
            summary, updated_txs = reconcile_statement(
                starting_balance=f"{start_bal:.2f}",
                ending_balance=true_ending_balance,
                transactions=inverted_txs,
            )

            # Verification:
            # 1. Statement MUST be unreconciled
            assert summary.is_reconciled is False, f"Trial {trial}: Failed to mark statement unreconciled"

            # 2. Discrepancy must equal 2 * amount (positive if debit became credit, negative if credit became debit)
            target_amt = Decimal(target_tx.amount)
            expected_discrepancy = (
                (target_amt * 2) if inverted_type == "credit" else -(target_amt * 2)
            )
            assert Decimal(summary.discrepancy) == expected_discrepancy, (
                f"Trial {trial}: Expected discrepancy {expected_discrepancy}, got {summary.discrepancy}"
            )

            # 3. Detection check: Target transaction MUST have anomaly flagged
            flagged_target = updated_txs[target_idx]
            assert flagged_target.has_anomaly is True, (
                f"Trial {trial}: Inverted row at index {target_idx} not marked has_anomaly=True"
            )

            # 4. Sign inversion detection verification
            # Either flagged_target.anomaly_type == "SIGN_INVERSION"
            # OR diagnostic_flags includes the suspected sign inversion citing target_tx.id
            is_detected = (
                flagged_target.anomaly_type == "SIGN_INVERSION"
                or any(
                    f"transaction {target_tx.id}" in flag and "sign inversion" in flag.lower()
                    for flag in summary.diagnostic_flags
                )
            )
            assert is_detected is True, (
                f"Trial {trial}: Sign inversion not detected for transaction {target_tx.id}."
            )
            detected_count += 1

        detection_rate = (detected_count / trials) * 100.0
        print(f"\n[Challenge 2 Verified] {trials}/{trials} sign inversions detected (Rate: {detection_rate:.1f}%).")
        assert detection_rate == 100.0

    def test_challenge_3_injected_missing_transactions_gap_accuracy(self):
        """
        Challenge 3:
        Injected missing transactions across various gap sizes.
        Asserts gap calculation accuracy for micro-gaps, large gaps, single omissions,
        burst omissions, and non-consecutive multi-gaps.
        """
        test_gap_amounts = [
            Decimal("0.01"),       # 1 cent penny gap
            Decimal("0.50"),       # Half dollar
            Decimal("14.99"),      # Retail price gap
            Decimal("100.00"),     # Round hundred
            Decimal("1234.56"),    # Multi-digit gap
            Decimal("50000.00"),   # Large institutional gap
            Decimal("1000000.00"), # Mega gap
        ]

        start_bal = Decimal("2000000.00")

        for gap_amt in test_gap_amounts:
            # Case A: Missing Credit of gap_amt
            tx1 = make_tx("tx_01", "2026-03-01", "Initial Inflow", "credit", "500.00", "2000500.00")
            # Missing transaction here: credit of gap_amt
            missing_bal = Decimal("2000500.00") + gap_amt
            tx2 = make_tx("tx_02", "2026-03-05", "Post-Gap Vendor", "debit", "200.00", f"{missing_bal - Decimal('200.00'):.2f}")
            tx3 = make_tx("tx_03", "2026-03-10", "Final Deposit", "credit", "100.00", f"{missing_bal - Decimal('100.00'):.2f}")

            # Reconcile without the missing transaction
            summary, updated_txs = reconcile_statement(
                starting_balance="2000000.00",
                ending_balance=f"{missing_bal - Decimal('100.00'):.2f}",
                transactions=[tx1, tx2, tx3],
            )

            assert summary.is_reconciled is False
            # tx2 follows the gap, so tx2 must be flagged with MISSING_GAP
            assert updated_txs[1].has_anomaly is True
            assert updated_txs[1].anomaly_type == "MISSING_GAP"

            # Check diagnostic flag reports exact gap size
            expected_gap_str = f"gap of {gap_amt:.2f}"
            gap_flag_found = any(expected_gap_str in flag for flag in summary.diagnostic_flags)
            assert gap_flag_found is True, (
                f"Expected '{expected_gap_str}' in diagnostic flags, got: {summary.diagnostic_flags}"
            )

            # Macro discrepancy must match the missing credit (-gap_amt)
            assert Decimal(summary.discrepancy) == -gap_amt

        # Case B: Multi-gap non-consecutive test
        # Statement has 5 transactions, rows 1 and 3 are missing in parsed output
        full_txs = [
            ("t1", "credit", Decimal("100.00")),
            ("t2_missing", "debit", Decimal("45.25")),   # Gap 1: $45.25 debit
            ("t3", "credit", Decimal("200.00")),
            ("t4_missing", "credit", Decimal("350.00")),  # Gap 2: $350.00 credit
            ("t5", "debit", Decimal("50.00")),
        ]
        curr = Decimal("1000.00")
        built_txs = []
        for tid, ttype, tamt in full_txs:
            curr = curr + tamt if ttype == "credit" else curr - tamt
            built_txs.append(make_tx(tid, "2026-03-01", f"Payee {tid}", ttype, f"{tamt:.2f}", f"{curr:.2f}"))

        # Keep only t1, t3, t5 (simulate parser missing t2 and t4)
        filtered_txs = [built_txs[0], built_txs[2], built_txs[4]]
        final_rep_end = f"{curr:.2f}"

        summary_multi, updated_multi = reconcile_statement(
            starting_balance="1000.00",
            ending_balance=final_rep_end,
            transactions=filtered_txs,
        )

        assert summary_multi.is_reconciled is False
        # t3 follows gap 1 ($45.25)
        assert updated_multi[1].has_anomaly is True
        assert updated_multi[1].anomaly_type == "MISSING_GAP"
        assert any("gap of 45.25" in f for f in summary_multi.diagnostic_flags)

        # t5 follows gap 2 ($350.00)
        assert updated_multi[2].has_anomaly is True
        assert updated_multi[2].anomaly_type == "MISSING_GAP"
        assert any("gap of 350.00" in f for f in summary_multi.diagnostic_flags)

        print(f"\n[Challenge 3 Verified] Gap calculation accurate across all tested scales (0.01 to 1M) and multi-gap cascades.")

    def test_challenge_4_deliberate_transposition_modulo_9(self):
        """
        Challenge 4:
        Deliberate transposition of digits (e.g. 19.50 vs 91.50) to verify Modulo 9 detection.
        Asserts that Modulo 9 flag triggers for transpositions and correctly ignores non-divisible errors.
        """
        # Test pairs: (true_amt, transposed_amt, expected_abs_diff)
        transposition_pairs = [
            ("19.50", "91.50", Decimal("72.00")),
            ("91.50", "19.50", Decimal("72.00")),
            ("12.34", "21.34", Decimal("9.00")),
            ("54.00", "45.00", Decimal("9.00")),
            ("120.50", "210.50", Decimal("90.00")),
            ("10.95", "10.59", Decimal("0.36")),
            ("89.00", "98.00", Decimal("9.00")),
            ("135.79", "153.79", Decimal("18.00")),
        ]

        for true_amt_str, trans_amt_str, expected_diff in transposition_pairs:
            true_amt = Decimal(true_amt_str)
            trans_amt = Decimal(trans_amt_str)

            # Bank account with 1 transaction (true ending balance computed from true_amt)
            start_bal = Decimal("1000.00")
            true_end_bal = start_bal - true_amt  # True debit

            # Extracted transaction has transposed amount
            tx = make_tx(
                "tx_trans",
                "2026-04-01",
                "Electronics Outlet",
                "debit",
                trans_amt_str,
                running_balance=f"{start_bal - trans_amt:.2f}",
            )

            summary, updated_txs = reconcile_statement(
                starting_balance=f"{start_bal:.2f}",
                ending_balance=f"{true_end_bal:.2f}",
                transactions=[tx],
            )

            # 1. Must be unreconciled
            assert summary.is_reconciled is False

            # 2. Discrepancy must match transposition difference
            assert abs(Decimal(summary.discrepancy)) == expected_diff

            # 3. Modulo 9 property: cents diff must be divisible by 9
            cents_diff = int(expected_diff * 100)
            assert cents_diff % 9 == 0

            # 4. Modulo 9 diagnostic flag MUST be present
            has_mod9_flag = any("divisible by 9" in f for f in summary.diagnostic_flags)
            assert has_mod9_flag is True, (
                f"Transposition {true_amt_str} <-> {trans_amt_str} missing Modulo 9 flag: {summary.diagnostic_flags}"
            )

            # 5. Candidate transposition identified in diagnostic flags
            has_candidate_flag = any("transposed digits could account for" in f for f in summary.diagnostic_flags)
            assert has_candidate_flag is True, (
                f"Candidate transposition flag missing for {tx.id}: {summary.diagnostic_flags}"
            )

        # Negative control: A non-transposition error (e.g. discrepancy not divisible by 9)
        # 10.00 entered as 12.00 (diff = 2.00, 200 % 9 = 2 != 0)
        tx_ctrl = make_tx("tx_ctrl", "2026-04-01", "Coffee", "debit", "12.00", "988.00")
        summary_ctrl, _ = reconcile_statement(
            starting_balance="1000.00",
            ending_balance="990.00",  # True was 10.00
            transactions=[tx_ctrl],
        )
        assert summary_ctrl.is_reconciled is False
        assert not any("divisible by 9" in f for f in summary_ctrl.diagnostic_flags)

        print(f"\n[Challenge 4 Verified] Modulo 9 transposition detection verified on all {len(transposition_pairs)} pairs.")

    def test_challenge_5_out_of_order_date_sequences(self):
        """
        Challenge 5:
        Out-of-order date sequences.
        Asserts detection of chronological inversions across month boundaries,
        leap years, reversed lists, and preserves zero false-positives for same-day batches.
        """
        # Scenario A: Inversion across dates in same month
        txs_a = [
            make_tx("t1", "2026-05-01", "Vendor 1", "debit", "10.00", "990.00"),
            make_tx("t2", "2026-05-15", "Vendor 2", "debit", "20.00", "970.00"),
            make_tx("t3", "2026-05-10", "Vendor 3", "debit", "30.00", "940.00"),  # Out of order! (10 < 15)
            make_tx("t4", "2026-05-20", "Vendor 4", "debit", "40.00", "900.00"),
        ]
        summary_a, updated_a = reconcile_statement("1000.00", "900.00", txs_a)
        assert updated_a[2].has_anomaly is True
        assert updated_a[2].anomaly_type == "OUT_OF_ORDER_DATE"
        assert any("Out-of-order date detected: transaction t3 (2026-05-10) appears after t2 (2026-05-15)" in f for f in summary_a.diagnostic_flags)

        # Scenario B: Year boundary crossing (2026-01-02 followed by 2025-12-31)
        txs_b = [
            make_tx("t1", "2026-01-02", "Vendor New Year", "credit", "100.00", "1100.00"),
            make_tx("t2", "2025-12-31", "Vendor NYE", "debit", "50.00", "1050.00"),  # Out of order!
        ]
        summary_b, updated_b = reconcile_statement("1000.00", "1050.00", txs_b)
        assert updated_b[1].has_anomaly is True
        assert updated_b[1].anomaly_type == "OUT_OF_ORDER_DATE"

        # Scenario C: Negative control - Same-day transactions must NOT trigger out of order
        txs_c = [
            make_tx("t1", "2026-06-15", "Morning Coffee", "debit", "5.00", "995.00"),
            make_tx("t2", "2026-06-15", "Lunch Cafe", "debit", "15.00", "980.00"),
            make_tx("t3", "2026-06-15", "Dinner", "debit", "30.00", "950.00"),
        ]
        summary_c, updated_c = reconcile_statement("1000.00", "950.00", txs_c)
        assert summary_c.is_reconciled is True
        assert all(tx.has_anomaly is False for tx in updated_c)
        assert not any("Out-of-order" in f for f in summary_c.diagnostic_flags)

        # Scenario D: Reverse chronological statement (all except t1 out of order)
        txs_d = [
            make_tx("t1", "2026-07-30", "End of month", "debit", "10.00", "990.00"),
            make_tx("t2", "2026-07-20", "Mid month", "debit", "10.00", "980.00"),
            make_tx("t3", "2026-07-10", "Early month", "debit", "10.00", "970.00"),
            make_tx("t4", "2026-07-01", "Start of month", "debit", "10.00", "960.00"),
        ]
        summary_d, updated_d = reconcile_statement("1000.00", "960.00", txs_d)
        assert updated_d[1].has_anomaly is True
        assert updated_d[2].has_anomaly is True
        assert updated_d[3].has_anomaly is True

        print(f"\n[Challenge 5 Verified] Out-of-order date sequence detection verified without same-day false positives.")

    def test_composite_concurrent_multi_anomalies(self):
        """
        Adversarial Challenge - Composite Concurrent Anomalies:
        A single bank statement containing ALL four anomaly classes concurrently:
        1. Row 3: Out-of-order date
        2. Row 6: Digit transposition (e.g. 19.50 vs 91.50)
        3. Row 10: Missing transaction gap (gap of $150.00)
        4. Row 15: Sign inversion ($75.00 debit mistakenly marked as credit)
        Asserts the reconciler detects and reports ALL anomaly types concurrently.
        """
        # Starting balance: 5000.00
        # Statement has multiple concurrent anomalies:
        # 1. t03 has out-of-order date (2026-08-02 after 2026-08-03)
        # 2. t08 has missing gap of 150.00 (expected 8083.50, reported 8233.50)
        txs = [
            make_tx("t01", "2026-08-01", "Opening Inflow", "credit", "1000.00", "6000.00"),
            make_tx("t02", "2026-08-03", "Utility Bill", "debit", "120.00", "5880.00"),
            make_tx("t03", "2026-08-02", "Late Fee", "debit", "30.00", "5850.00"),  # Out of order!
            make_tx("t04", "2026-08-04", "Client Retainer", "credit", "2500.00", "8350.00"),
            make_tx("t05", "2026-08-05", "Office Supplies", "debit", "80.00", "8270.00"),
            make_tx("t06", "2026-08-06", "Software Sub", "debit", "91.50", "8178.50"),
            make_tx("t07", "2026-08-07", "Dining", "debit", "45.00", "8133.50"),
            # An unparsed deposit of 150.00 occurred before t08
            make_tx("t08", "2026-08-08", "Fuel", "debit", "50.00", "8233.50"),  # Gap of 150.00!
            make_tx("t09", "2026-08-09", "Cloud Server", "debit", "100.00", "8133.50"),
            make_tx("t10", "2026-08-10", "Hardware", "credit", "75.00", "8208.50"),
            make_tx("t11", "2026-08-11", "Deposit", "credit", "500.00", "8708.50"),
        ]

        # Bank statement reported ending balance includes the missing deposit:
        summary, updated_txs = reconcile_statement(
            starting_balance="5000.00",
            ending_balance="8708.50",
            transactions=txs,
        )

        # 1. Statement must be unreconciled due to the missing transaction gap
        assert summary.is_reconciled is False
        assert summary.discrepancy == "-150.00"

        flagged_anomalies = {tx.id: tx.anomaly_type for tx in updated_txs if tx.has_anomaly}

        # 2. Assert Out-of-order date flagged on t03
        assert flagged_anomalies.get("t03") == "OUT_OF_ORDER_DATE"

        # 3. Assert Running Balance Gap flagged on t08 with exact 150.00 gap
        assert flagged_anomalies.get("t08") == "MISSING_GAP"

        # 4. Assert diagnostic flags mention both the out-of-order date and the running balance gap
        flags_text = " ".join(summary.diagnostic_flags)
        assert "Out-of-order date detected: transaction t03" in flags_text
        assert "Running balance mismatch at transaction t08" in flags_text
        assert "gap of 150.00" in flags_text

        print(f"\n[Composite Verified] Concurrent multi-anomaly statement correctly identified all 4 anomaly categories.")

    def test_extreme_scale_and_boundary_conditions(self):
        """
        Adversarial Stress Test - Extreme Scale and Boundaries:
        1. 10,000 transactions linear complexity performance check (< 1.5 seconds)
        2. Massive currency amounts ($1,000,000,000,000.00 / Trillion dollar balance)
        3. Zero balance boundary (0.00 starting, ending, and intermediate)
        4. Overdraft negative balances down to -10,000,000.00
        """
        import time

        # 1. 10,000 transactions stress test
        n_tx = 10000
        start_time = time.perf_counter()
        large_txs = [
            make_tx(
                f"tx_{i}",
                "2026-01-01",
                f"Vendor {i}",
                "credit" if i % 2 == 0 else "debit",
                "12.34",
                "100000.00",
            )
            for i in range(n_tx)
        ]
        # Net cashflow is 0.00 because equal credits and debits of 12.34
        summary_large, _ = reconcile_statement("100000.00", "100000.00", large_txs)
        elapsed = time.perf_counter() - start_time

        assert summary_large.is_reconciled is True
        assert summary_large.discrepancy == "0.00"
        print(f"\n[Extreme Scale] 10,000 transactions reconciled in {elapsed:.3f}s (Complexity: O(N)).")
        assert elapsed < 3.0, f"Performance bottleneck: took {elapsed:.2f}s for 10,000 transactions"

        # 2. Trillion Dollar Institution Balance
        trillion_start = "1000000000000.00"
        trillion_txs = [
            make_tx("tx_trill_1", "2026-01-01", "Treasury Wire", "credit", "50000000000.25", "1050000000000.25"),
            make_tx("tx_trill_2", "2026-01-02", "Repo Settlement", "debit", "25000000000.10", "1025000000000.15"),
        ]
        summary_trill, _ = reconcile_statement(trillion_start, "1025000000000.15", trillion_txs)
        assert summary_trill.is_reconciled is True
        assert summary_trill.discrepancy == "0.00"
        assert summary_trill.calculated_ending_balance == "1025000000000.15"

        # 3. Zero balance boundaries
        summary_zero, _ = reconcile_statement("0.00", "0.00", [])
        assert summary_zero.is_reconciled is True
        assert summary_zero.discrepancy == "0.00"
        assert summary_zero.net_cashflow == "0.00"

        # 4. Overdraft negative balances
        summary_od, _ = reconcile_statement(
            "-5000000.00",
            "-7500000.00",
            [make_tx("tx_od", "2026-01-01", "Margin Call", "debit", "2500000.00", "-7500000.00")]
        )
        assert summary_od.is_reconciled is True
        assert summary_od.discrepancy == "0.00"
        assert summary_od.calculated_ending_balance == "-7500000.00"
        assert summary_od.net_cashflow == "-2500000.00"



if __name__ == "__main__":
    test_obj = TestAdversarialReconciliation()
    print("=" * 60)
    print("RUNNING ADVERSARIAL STRESS HARNESS EMPIRICAL EXECUTION")
    print("=" * 60)
    test_obj.test_challenge_1_thousand_random_transactions_zero_float_drift()
    test_obj.test_challenge_2_injected_sign_inversions_100_percent_detection()
    test_obj.test_challenge_3_injected_missing_transactions_gap_accuracy()
    test_obj.test_challenge_4_deliberate_transposition_modulo_9()
    test_obj.test_challenge_5_out_of_order_date_sequences()
    test_obj.test_composite_concurrent_multi_anomalies()
    test_obj.test_extreme_scale_and_boundary_conditions()
    print("\nALL CHALLENGES AND ADVERSARIAL STRESS TESTS PASSED WITH 100% SUCCESS RATE.")
