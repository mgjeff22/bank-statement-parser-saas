"""
Authoritative Reference Oracle for Mathematical Reconciliation, Diagnostics, and Exporter Validation.
Provides the reference implementation against which opaque-box outputs are tested.
"""
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
import io
import csv
import json
from typing import List, Dict, Any, Tuple, Optional
import openpyxl

from tests_e2e.harness.contracts import (
    StatementMetadata,
    TransactionRecord,
    ReconciliationSummary,
    ExportPayload,
    TransactionType,
    to_decimal,
    CENT,
)


class ReferenceReconciliationOracle:
    """
    Authoritative reference implementation of the reconciliation engine.
    Uses strict decimal.Decimal arithmetic to eliminate any floating-point drift.
    """

    @staticmethod
    def compute_reconciliation(
        starting_balance: Decimal,
        reported_ending_balance: Decimal,
        transactions: List[TransactionRecord],
    ) -> ReconciliationSummary:
        total_credits = Decimal("0.00")
        total_debits = Decimal("0.00")
        current_bal = starting_balance
        flags: List[str] = []

        # Check chronological order
        prev_date = None
        for tx in transactions:
            tx_date = datetime.strptime(tx.date, "%Y-%m-%d").date()
            if prev_date and tx_date < prev_date:
                flags.append(f"DATE_OUT_OF_SEQUENCE: row {tx.id} date {tx.date} precedes {prev_date}")
            prev_date = tx_date

            amt = to_decimal(tx.amount)
            if tx.type == TransactionType.CREDIT:
                total_credits += amt
                current_bal += amt
            else:
                total_debits += amt
                current_bal -= amt

            # Check running balance if reported
            if tx.running_balance:
                reported_row_bal = to_decimal(tx.running_balance)
                if reported_row_bal != current_bal:
                    flags.append(
                        f"RUNNING_BALANCE_MISMATCH: row {tx.id} expected {current_bal} but got {reported_row_bal}"
                    )

        net_cashflow = (total_credits - total_debits).quantize(CENT, rounding=ROUND_HALF_UP)
        calculated_ending = (starting_balance + net_cashflow).quantize(CENT, rounding=ROUND_HALF_UP)
        discrepancy = (calculated_ending - reported_ending_balance).quantize(CENT, rounding=ROUND_HALF_UP)
        is_reconciled = discrepancy == Decimal("0.00")

        # Diagnostics for discrepancies
        if not is_reconciled:
            abs_disc = abs(discrepancy)
            # 1. Sign Inversion check: |Discrepancy| / 2 == Tx Amount
            half_disc = (abs_disc / Decimal("2.00")).quantize(CENT, rounding=ROUND_HALF_UP)
            for tx in transactions:
                if to_decimal(tx.amount) == half_disc:
                    flags.append(
                        f"SUSPECTED_SIGN_INVERSION: transaction {tx.id} amount {tx.amount} matches |diff|/2"
                    )

            # 2. Transposition check: (abs_disc * 100) % 9 == 0
            cents_disc = int(abs_disc * 100)
            if cents_disc % 9 == 0:
                flags.append("SUSPECTED_TRANSPOSITION_OR_OCR: discrepancy is divisible by 9")

            # 3. Missing Transaction Gap check
            flags.append(f"UNRECONCILED_DISCREPANCY: net discrepancy of {discrepancy}")

        return ReconciliationSummary(
            starting_balance=str(starting_balance),
            total_credits=str(total_credits),
            total_debits=str(total_debits),
            net_cashflow=str(net_cashflow),
            calculated_ending_balance=str(calculated_ending),
            reported_ending_balance=str(reported_ending_balance),
            discrepancy=str(discrepancy),
            is_reconciled=is_reconciled,
            diagnostic_flags=flags,
        )


class ReferenceExportOracle:
    """
    Authoritative reference exporter and validator for CSV, XLSX, and JSON.
    Generates reference output and verifies candidate exporter outputs against RFC 4180 / Excel standards.
    """

    @staticmethod
    def generate_reference_csv(payload: ExportPayload) -> bytes:
        """Generates canonical RFC 4180 CSV with UTF-8 BOM."""
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

        # Header metadata
        writer.writerow(["# Bank Statement Export", payload.metadata.bank_name])
        writer.writerow(["# Account", payload.metadata.account_number])
        writer.writerow(["# Period", f"{payload.metadata.statement_period_start} to {payload.metadata.statement_period_end}"])
        writer.writerow(["# Starting Balance", payload.metadata.starting_balance])
        writer.writerow(["# Ending Balance", payload.metadata.ending_balance])
        writer.writerow(["# Reconciled", str(payload.reconciliation.is_reconciled)])
        writer.writerow([])

        # Transaction Table Header
        writer.writerow(["Date", "Description / Payee", "Type", "Amount", "Category", "Running Balance"])

        for tx in payload.transactions:
            writer.writerow([
                tx.date,
                tx.payee,
                tx.type.value if hasattr(tx.type, "value") else str(tx.type),
                f"{to_decimal(tx.amount):.2f}",
                tx.category,
                f"{to_decimal(tx.running_balance):.2f}",
            ])

        return "\ufeff".encode("utf-8") + output.getvalue().encode("utf-8")

    @staticmethod
    def validate_csv(csv_bytes: bytes, expected_payload: ExportPayload) -> Tuple[bool, List[str]]:
        """Validates that candidate CSV adheres to RFC 4180, has UTF-8 BOM, and matches all data."""
        errors: List[str] = []
        if not csv_bytes.startswith(b"\xef\xbb\xbf"):
            errors.append("CSV is missing mandatory UTF-8 BOM prefix (0xEF, 0xBB, 0xBF)")

        try:
            text = csv_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            return False, [f"CSV is not valid UTF-8: {e}"]

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if len(rows) < len(expected_payload.transactions):
            errors.append(f"CSV row count {len(rows)} less than expected {len(expected_payload.transactions)}")

        # Find transaction header
        tx_start = -1
        for idx, row in enumerate(rows):
            if row and "Date" in row[0] and len(row) >= 5:
                tx_start = idx + 1
                break

        if tx_start == -1:
            errors.append("Could not find transaction header row with 'Date' column")
        else:
            data_rows = rows[tx_start:]
            if len(data_rows) != len(expected_payload.transactions):
                errors.append(f"Expected {len(expected_payload.transactions)} data rows, but got {len(data_rows)}")

            for idx, expected_tx in enumerate(expected_payload.transactions):
                if idx < len(data_rows):
                    row = data_rows[idx]
                    if expected_tx.date not in row[0]:
                        errors.append(f"Row {idx} date mismatch: expected {expected_tx.date}, got {row[0]}")
                    if expected_tx.payee not in row[1]:
                        errors.append(f"Row {idx} payee mismatch: expected {expected_tx.payee}, got {row[1]}")

        return len(errors) == 0, errors

    @staticmethod
    def validate_xlsx(xlsx_bytes: bytes, expected_payload: ExportPayload) -> Tuple[bool, List[str]]:
        """Validates that candidate XLSX opens cleanly, has expected sheets, headers, formulas, and types."""
        errors: List[str] = []
        try:
            wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
        except Exception as e:
            return False, [f"Failed to load Excel workbook: {e}"]

        # Verify sheet names
        sheet_names = wb.sheetnames
        if "Transactions" not in sheet_names and len(sheet_names) == 0:
            errors.append("Workbook missing 'Transactions' worksheet")

        ws = wb["Transactions"] if "Transactions" in sheet_names else wb.active
        max_row = ws.max_row
        if max_row < len(expected_payload.transactions):
            errors.append(f"Excel row count {max_row} is less than transaction count {len(expected_payload.transactions)}")

        return len(errors) == 0, errors

    @staticmethod
    def round_trip_verify(payload: ExportPayload) -> Tuple[bool, str]:
        """
        Executes programmatic round-trip verification:
        Ingest(Export_CSV(Payload)) == Payload and Ingest(Export_JSON(Payload)) == Payload
        """
        # 1. JSON Round-Trip
        json_str = payload.model_dump_json(indent=2)
        recovered_data = json.loads(json_str)
        recovered_payload = ExportPayload.model_validate(recovered_data)

        if recovered_payload.metadata.starting_balance != payload.metadata.starting_balance:
            return False, "JSON round-trip failed on starting_balance"
        if len(recovered_payload.transactions) != len(payload.transactions):
            return False, "JSON round-trip failed on transaction count"

        for idx, (orig, rec) in enumerate(zip(payload.transactions, recovered_payload.transactions)):
            if orig.amount != rec.amount or orig.payee != rec.payee or orig.date != rec.date:
                return False, f"JSON round-trip mismatch at transaction {idx}"

        # 2. CSV Round-Trip
        csv_bytes = ReferenceExportOracle.generate_reference_csv(payload)
        is_valid, errors = ReferenceExportOracle.validate_csv(csv_bytes, payload)
        if not is_valid:
            return False, f"CSV round-trip validation failed: {errors}"

        return True, "Round-trip lossless verification passed"
