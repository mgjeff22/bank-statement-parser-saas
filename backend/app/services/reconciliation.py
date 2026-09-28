"""
Strict Decimal Mathematical Reconciliation Engine.

Adheres strictly to zero floating-point drift using decimal.Decimal,
ROUND_HALF_UP rounding, and comprehensive anomaly diagnostic rules:
- Starting Balance + Total Credits - Total Debits == Ending Balance
- Net Cashflow = Total Credits - Total Debits
- Sequential running balance verification
- Sign Inversion detection (|Discrepancy| / 2 match)
- Missing Transaction Gap detection
- Out-of-Order Date sequence detection
- Digit Transposition check (Modulo 9)
"""
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Tuple, Union

from app.schemas.reconciliation import ReconciliationSummary
from app.schemas.transaction import TransactionRecord


CENT = Decimal("0.01")


def to_decimal(val: Union[str, int, float, Decimal]) -> Decimal:
    """
    Safely converts a value to Decimal quantized to 2 decimal places using ROUND_HALF_UP.
    Converts numbers via string to avoid binary floating-point inaccuracy.
    Supports:
    - Accounting parentheses: '(150.00)' -> Decimal('-150.00')
    - Currency symbols: '$', '€', '£', '¥', 'CAD', 'EUR', 'GBP', 'USD'
    - Explicit signs: '-$150.00', '$-150.00', '+$150.00', '150.00-'
    - European comma decimals: '1.250,50' -> Decimal('1250.50'), '150,50' -> Decimal('150.50')
    """
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val.quantize(CENT, rounding=ROUND_HALF_UP)
    if isinstance(val, (int, float)):
        return Decimal(f"{val:.4f}").quantize(CENT, rounding=ROUND_HALF_UP)

    val_str = str(val).strip()
    if not val_str:
        return Decimal("0.00")

    # Detect negative indicator: accounting parentheses or minus sign
    is_negative = ("(" in val_str and ")" in val_str) or ("-" in val_str)

    # Strip currency symbols, currency codes, letters, parentheses, signs, spaces
    num_str = re.sub(r"[^\d.,]", "", val_str)
    if not num_str or num_str == ".":
        return Decimal("0.00")

    # Handle European vs American comma/period decimal separators
    if "," in num_str and "." in num_str:
        if num_str.rfind(",") > num_str.rfind("."):
            # Comma is decimal separator (e.g. 1.250,50)
            num_str = num_str.replace(".", "").replace(",", ".")
        else:
            # Period is decimal separator (e.g. 1,250.50)
            num_str = num_str.replace(",", "")
    elif "," in num_str and "." not in num_str:
        # Single separator with comma: check if 2 decimal places (cents)
        parts = num_str.split(",")
        if len(parts) == 2 and len(parts[1]) == 2:
            num_str = f"{parts[0]}.{parts[1]}"
        else:
            num_str = num_str.replace(",", "")

    try:
        dec = Decimal(num_str).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

    return -dec if is_negative else dec



def format_decimal(val: Decimal) -> str:
    """Formats Decimal to exact 2-decimal-place string."""
    return f"{val.quantize(CENT, rounding=ROUND_HALF_UP):.2f}"


def reconcile_statement(
    starting_balance: Union[str, Decimal],
    ending_balance: Union[str, Decimal],
    transactions: List[TransactionRecord],
) -> Tuple[ReconciliationSummary, List[TransactionRecord]]:
    """
    Executes formal mathematical reconciliation across all transactions.
    Returns (ReconciliationSummary, updated transactions list with anomaly flags).
    """
    start_dec = to_decimal(starting_balance)
    rep_end_dec = to_decimal(ending_balance)

    total_credits = Decimal("0.00")
    total_debits = Decimal("0.00")

    # Clone transactions or work on copy to avoid unintended mutations
    updated_txs: List[TransactionRecord] = []
    for tx in transactions:
        tx_dict = tx.model_dump()
        updated_txs.append(TransactionRecord(**tx_dict))

    # 1. Macro Totals
    for tx in updated_txs:
        amt = to_decimal(tx.amount)
        if tx.type == "credit":
            total_credits += amt
        else:
            total_debits += amt

    net_cashflow = (total_credits - total_debits).quantize(CENT, rounding=ROUND_HALF_UP)
    calc_end_dec = (start_dec + net_cashflow).quantize(CENT, rounding=ROUND_HALF_UP)
    discrepancy = (calc_end_dec - rep_end_dec).quantize(CENT, rounding=ROUND_HALF_UP)
    is_reconciled = discrepancy == Decimal("0.00")

    diagnostic_flags: List[str] = []

    # 2. Sequential Running Balance Verification & Gap Detection
    running_bal = start_dec
    for i, tx in enumerate(updated_txs):
        amt = to_decimal(tx.amount)
        expected_running = (
            running_bal + amt if tx.type == "credit" else running_bal - amt
        ).quantize(CENT, rounding=ROUND_HALF_UP)

        rep_running = to_decimal(tx.running_balance) if tx.running_balance else None

        if rep_running is not None:
            # Check if reported running balance matches calculated running balance
            if rep_running != expected_running:
                step_gap = (rep_running - expected_running).quantize(CENT, rounding=ROUND_HALF_UP)
                tx.has_anomaly = True
                tx.anomaly_type = "MISSING_GAP"
                diagnostic_flags.append(
                    f"Running balance mismatch at transaction {tx.id} ({tx.date}, {tx.payee}): "
                    f"expected {format_decimal(expected_running)}, reported {format_decimal(rep_running)} "
                    f"(gap of {format_decimal(abs(step_gap))})"
                )
                # Re-anchor running balance to reported balance to avoid cascading errors
                running_bal = rep_running
            else:
                running_bal = expected_running
        else:
            running_bal = expected_running

    # 3. Out-of-Order Date Sequence Detection
    for i in range(1, len(updated_txs)):
        prev_tx = updated_txs[i - 1]
        curr_tx = updated_txs[i]
        if curr_tx.date and prev_tx.date and curr_tx.date < prev_tx.date:
            curr_tx.has_anomaly = True
            if not curr_tx.anomaly_type:
                curr_tx.anomaly_type = "OUT_OF_ORDER_DATE"
            diagnostic_flags.append(
                f"Out-of-order date detected: transaction {curr_tx.id} ({curr_tx.date}) "
                f"appears after {prev_tx.id} ({prev_tx.date})"
            )

    # 4. Sign Inversion Detection
    # If discrepancy is non-zero, check if half the absolute discrepancy matches any transaction amount
    if discrepancy != Decimal("0.00"):
        half_disc = (abs(discrepancy) / Decimal("2.0")).quantize(CENT, rounding=ROUND_HALF_UP)
        found_inversion = False
        for tx in updated_txs:
            amt = to_decimal(tx.amount)
            if amt == half_disc:
                # If discrepancy > 0, calc_end is higher than reported_end.
                # A debit mistakenly labeled as credit inflates calc_end by 2 * amt.
                # If discrepancy < 0, a credit mistakenly labeled as debit deflates calc_end by 2 * amt.
                if (discrepancy > Decimal("0.00") and tx.type == "credit") or (
                    discrepancy < Decimal("0.00") and tx.type == "debit"
                ):
                    tx.has_anomaly = True
                    tx.anomaly_type = "SIGN_INVERSION"
                    target_type = "debit" if tx.type == "credit" else "credit"
                    diagnostic_flags.append(
                        f"Suspected sign inversion: transaction {tx.id} ({tx.date}, {tx.payee}) "
                        f"with amount {format_decimal(amt)} is marked as '{tx.type}'. "
                        f"Switching to '{target_type}' would resolve the discrepancy."
                    )
                    found_inversion = True

    # 5. Digit Transposition Check (Modulo 9 Test)
    if discrepancy != Decimal("0.00"):
        cents_diff = int(abs(discrepancy) * 100)
        if cents_diff > 0 and cents_diff % 9 == 0:
            diagnostic_flags.append(
                f"Potential digit transposition or OCR optical confusion: "
                f"discrepancy of {format_decimal(abs(discrepancy))} is divisible by 9."
            )
            # Scan for candidate transactions where transposition of digits could equal discrepancy
            for tx in updated_txs:
                amt = to_decimal(tx.amount)
                # Test adjacent digit swaps on amount string
                amt_str = f"{amt:.2f}".replace(".", "")
                for j in range(len(amt_str) - 1):
                    if amt_str[j] != amt_str[j + 1]:
                        swapped = list(amt_str)
                        swapped[j], swapped[j + 1] = swapped[j + 1], swapped[j]
                        swapped_cents = int("".join(swapped))
                        orig_cents = int(amt_str)
                        swap_diff = Decimal(abs(swapped_cents - orig_cents)) / Decimal("100.00")
                        if swap_diff == abs(discrepancy):
                            tx.has_anomaly = True
                            if not tx.anomaly_type:
                                tx.anomaly_type = "TRANSPOSITION"
                            diagnostic_flags.append(
                                f"Digit transposition candidate in transaction {tx.id} ({tx.payee}): "
                                f"amount {tx.amount} transposed digits could account for {format_decimal(abs(discrepancy))} discrepancy."
                            )
                            break

    # 6. Overall Discrepancy Status Flag
    if not is_reconciled:
        diagnostic_flags.append(
            f"Statement unreconciled: Calculated Ending Balance {format_decimal(calc_end_dec)} "
            f"differs from Reported Ending Balance {format_decimal(rep_end_dec)} "
            f"by discrepancy {format_decimal(discrepancy)}."
        )
    else:
        if not diagnostic_flags:
            diagnostic_flags.append("Statement reconciled successfully: Ending balance matches calculated net cashflow.")

    summary = ReconciliationSummary(
        starting_balance=format_decimal(start_dec),
        total_credits=format_decimal(total_credits),
        total_debits=format_decimal(total_debits),
        net_cashflow=format_decimal(net_cashflow),
        calculated_ending_balance=format_decimal(calc_end_dec),
        reported_ending_balance=format_decimal(rep_end_dec),
        discrepancy=format_decimal(discrepancy),
        is_reconciled=is_reconciled,
        diagnostic_flags=diagnostic_flags,
    )

    return summary, updated_txs
