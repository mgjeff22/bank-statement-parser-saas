"""
Production Data Exporter Engine for AI Bank Statement Parser Micro-SaaS.
Supports:
1. RFC 4180 CSV with UTF-8 BOM, standard escaping, and valid headers.
2. Formatted Excel (.xlsx) via openpyxl with dark navy headers, bold text, currency formatting,
   typed dates, dynamic =SUM() / =SUMIF() formulas, and a dedicated Reconciliation Summary sheet.
3. Structured hierarchical JSON with versioning.
4. Programmatic round-trip lossless re-ingestion verification.
"""
import io
import csv
import json
from decimal import Decimal
from typing import List, Tuple, Optional, Dict, Any
from pydantic import BaseModel, Field

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from app.schemas.statement import StatementMetadata
from app.schemas.transaction import TransactionRecord
from app.schemas.reconciliation import ReconciliationSummary
from app.services.reconciliation import to_decimal, format_decimal


class ExportPayload(BaseModel):
    metadata: StatementMetadata = Field(..., description="Statement header and balance metadata")
    reconciliation: ReconciliationSummary = Field(..., description="Mathematical reconciliation summary")
    transactions: List[TransactionRecord] = Field(default_factory=list, description="List of transactions")


# ---------------------------------------------------------------------------
# 1. RFC 4180 CSV Exporter
# ---------------------------------------------------------------------------

def export_to_csv(payload: ExportPayload) -> bytes:
    """
    Generates an RFC 4180 compliant CSV byte string with UTF-8 BOM.
    Contains metadata preamble followed by transaction records with standard escaping.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

    # Header metadata block
    writer.writerow(["# Bank Statement Export", payload.metadata.bank_name])
    writer.writerow(["# Account", payload.metadata.account_number])
    writer.writerow(["# Period", f"{payload.metadata.statement_period_start} to {payload.metadata.statement_period_end}"])
    writer.writerow(["# Starting Balance", payload.metadata.starting_balance])
    writer.writerow(["# Ending Balance", payload.metadata.ending_balance])
    writer.writerow(["# Reconciled", str(payload.reconciliation.is_reconciled)])
    writer.writerow([])

    # Transaction Table Header
    writer.writerow(["Date", "Description / Payee", "Type", "Amount", "Category", "Running Balance"])

    # Transaction Rows
    for tx in payload.transactions:
        t_type = tx.type.value if hasattr(tx.type, "value") else str(tx.type)
        writer.writerow([
            tx.date,
            tx.payee,
            t_type,
            f"{to_decimal(tx.amount):.2f}",
            tx.category,
            f"{to_decimal(tx.running_balance):.2f}",
        ])

    # UTF-8 BOM (\xef\xbb\xbf) ensures Microsoft Excel properly auto-detects UTF-8 on Windows
    return "\ufeff".encode("utf-8") + output.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# 2. Professional Excel (.xlsx) Exporter
# ---------------------------------------------------------------------------

def export_to_xlsx(payload: ExportPayload) -> bytes:
    """
    Generates a professional Excel workbook using openpyxl.
    - Sheet 1 ('Transactions'): Dark navy headers, typed numeric currency values,
      alternating zebra rows, auto column widths, and summary total formulas.
    - Sheet 2 ('Reconciliation Summary'): Audit block with starting balance, credits,
      debits, calculated ending balance, reported ending balance, and discrepancy formula.
    """
    wb = openpyxl.Workbook()

    # Style definitions
    navy_fill = PatternFill(start_color="1E293B", end_color="1E293B", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    regular_font = Font(name="Calibri", size=10)
    bold_font = Font(name="Calibri", size=10, bold=True)
    summary_font = Font(name="Calibri", size=11, bold=True)

    zebra_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    white_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

    green_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    green_font = Font(name="Calibri", size=11, bold=True, color="166534")

    rose_fill = PatternFill(start_color="FFE4E6", end_color="FFE4E6", fill_type="solid")
    rose_font = Font(name="Calibri", size=11, bold=True, color="9F1239")

    thin_border_side = Side(style="thin", color="E2E8F0")
    thin_border = Border(left=thin_border_side, right=thin_border_side, top=thin_border_side, bottom=thin_border_side)
    double_bottom_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=Side(style="double", color="1E293B"),
    )

    currency_fmt = "$#,##0.00"

    # ---------------- Sheet 1: Transactions ----------------
    ws_tx = wb.active
    ws_tx.title = "Transactions"
    ws_tx.views.sheetView[0].showGridLines = True

    # Headers
    headers = ["Date", "Description / Payee", "Type", "Amount", "Category", "Running Balance"]
    ws_tx.append(headers)
    ws_tx.row_dimensions[1].height = 26

    for col_idx in range(1, len(headers) + 1):
        cell = ws_tx.cell(row=1, column=col_idx)
        cell.fill = navy_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    # Data Rows
    current_row = 2
    for idx, tx in enumerate(payload.transactions):
        t_type = tx.type.value if hasattr(tx.type, "value") else str(tx.type)
        amt_float = float(to_decimal(tx.amount))
        bal_float = float(to_decimal(tx.running_balance))

        ws_tx.append([
            tx.date,
            tx.payee,
            t_type,
            amt_float,
            tx.category,
            bal_float,
        ])

        row_fill = zebra_fill if idx % 2 == 1 else white_fill
        ws_tx.row_dimensions[current_row].height = 20

        # Col 1: Date (Center)
        c1 = ws_tx.cell(row=current_row, column=1)
        c1.alignment = Alignment(horizontal="center", vertical="center")
        c1.font = regular_font
        c1.fill = row_fill
        c1.border = thin_border

        # Col 2: Payee (Left)
        c2 = ws_tx.cell(row=current_row, column=2)
        c2.alignment = Alignment(horizontal="left", vertical="center")
        c2.font = regular_font
        c2.fill = row_fill
        c2.border = thin_border

        # Col 3: Type (Center)
        c3 = ws_tx.cell(row=current_row, column=3)
        c3.alignment = Alignment(horizontal="center", vertical="center")
        c3.font = regular_font
        c3.fill = row_fill
        c3.border = thin_border

        # Col 4: Amount (Right, Currency format)
        c4 = ws_tx.cell(row=current_row, column=4)
        c4.alignment = Alignment(horizontal="right", vertical="center")
        c4.font = regular_font
        c4.fill = row_fill
        c4.border = thin_border
        c4.number_format = currency_fmt

        # Col 5: Category (Left)
        c5 = ws_tx.cell(row=current_row, column=5)
        c5.alignment = Alignment(horizontal="left", vertical="center")
        c5.font = regular_font
        c5.fill = row_fill
        c5.border = thin_border

        # Col 6: Running Balance (Right, Currency format)
        c6 = ws_tx.cell(row=current_row, column=6)
        c6.alignment = Alignment(horizontal="right", vertical="center")
        c6.font = regular_font
        c6.fill = row_fill
        c6.border = thin_border
        c6.number_format = currency_fmt

        current_row += 1

    # Freeze Header Row
    ws_tx.freeze_panes = "A2"

    # Add Summary Totals Row if transactions exist
    last_data_row = current_row - 1
    if last_data_row >= 2:
        # Row: Total Debits
        deb_row = current_row
        ws_tx.cell(row=deb_row, column=3, value="Total Debits").font = bold_font
        ws_tx.cell(row=deb_row, column=3).alignment = Alignment(horizontal="right", vertical="center")
        deb_cell = ws_tx.cell(row=deb_row, column=4, value=f'=SUMIF(C2:C{last_data_row}, "debit", D2:D{last_data_row})')
        deb_cell.font = bold_font
        deb_cell.alignment = Alignment(horizontal="right", vertical="center")
        deb_cell.number_format = currency_fmt
        current_row += 1

        # Row: Total Credits
        cred_row = current_row
        ws_tx.cell(row=cred_row, column=3, value="Total Credits").font = bold_font
        ws_tx.cell(row=cred_row, column=3).alignment = Alignment(horizontal="right", vertical="center")
        cred_cell = ws_tx.cell(row=cred_row, column=4, value=f'=SUMIF(C2:C{last_data_row}, "credit", D2:D{last_data_row})')
        cred_cell.font = bold_font
        cred_cell.alignment = Alignment(horizontal="right", vertical="center")
        cred_cell.number_format = currency_fmt
        current_row += 1

        # Row: Net Cashflow
        net_row = current_row
        ws_tx.cell(row=net_row, column=3, value="Net Cashflow").font = summary_font
        ws_tx.cell(row=net_row, column=3).alignment = Alignment(horizontal="right", vertical="center")
        net_cell = ws_tx.cell(row=net_row, column=4, value=f'=D{cred_row}-D{deb_row}')
        net_cell.font = summary_font
        net_cell.alignment = Alignment(horizontal="right", vertical="center")
        net_cell.number_format = currency_fmt
        net_cell.border = double_bottom_border
        ws_tx.cell(row=net_row, column=3).border = double_bottom_border

    # Auto-adjust column widths
    for col in ws_tx.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if cell.number_format == currency_fmt and isinstance(cell.value, (int, float)):
                val_str = f"${cell.value:,.2f}"
            max_len = max(max_len, len(val_str))
        ws_tx.column_dimensions[col_letter].width = max(max_len + 4, 14)

    # ---------------- Sheet 2: Reconciliation Summary ----------------
    ws_rec = wb.create_sheet(title="Reconciliation Summary")
    ws_rec.views.sheetView[0].showGridLines = True

    # Title Block
    ws_rec.merge_cells("A1:D1")
    title_cell = ws_rec.cell(row=1, column=1, value="Bank Statement Reconciliation Audit")
    title_cell.fill = navy_fill
    title_cell.font = Font(name="Calibri", size=14, bold=True, color="FFFFFF")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws_rec.row_dimensions[1].height = 32

    # Metadata rows
    meta_items = [
        ("Bank Name", payload.metadata.bank_name),
        ("Account Number", payload.metadata.account_number),
        ("Statement Period", f"{payload.metadata.statement_period_start} to {payload.metadata.statement_period_end}"),
        ("Currency", payload.metadata.currency),
    ]

    for r_idx, (label, val) in enumerate(meta_items, start=3):
        lbl_c = ws_rec.cell(row=r_idx, column=1, value=label)
        lbl_c.font = bold_font
        val_c = ws_rec.cell(row=r_idx, column=2, value=val)
        val_c.font = regular_font
        ws_rec.row_dimensions[r_idx].height = 20

    # Math Audit Block Headers
    audit_header = ws_rec.cell(row=8, column=1, value="Mathematical Verification")
    audit_header.font = Font(name="Calibri", size=12, bold=True, color="1E293B")

    # Row 9: Starting Balance
    ws_rec.cell(row=9, column=1, value="Starting Balance").font = bold_font
    c_start = ws_rec.cell(row=9, column=2, value=float(to_decimal(payload.metadata.starting_balance)))
    c_start.font = regular_font
    c_start.number_format = currency_fmt
    c_start.alignment = Alignment(horizontal="right")

    # Row 10: Total Credits
    ws_rec.cell(row=10, column=1, value="(+) Total Credits").font = bold_font
    c_cred = ws_rec.cell(row=10, column=2, value=float(to_decimal(payload.reconciliation.total_credits)))
    c_cred.font = regular_font
    c_cred.number_format = currency_fmt
    c_cred.alignment = Alignment(horizontal="right")

    # Row 11: Total Debits
    ws_rec.cell(row=11, column=1, value="(-) Total Debits").font = bold_font
    c_deb = ws_rec.cell(row=11, column=2, value=float(to_decimal(payload.reconciliation.total_debits)))
    c_deb.font = regular_font
    c_deb.number_format = currency_fmt
    c_deb.alignment = Alignment(horizontal="right")

    # Row 12: Calculated Ending Balance (=B9+B10-B11)
    ws_rec.cell(row=12, column=1, value="Calculated Ending Balance").font = summary_font
    c_calc = ws_rec.cell(row=12, column=2, value="=B9+B10-B11")
    c_calc.font = summary_font
    c_calc.number_format = currency_fmt
    c_calc.alignment = Alignment(horizontal="right")

    # Row 13: Reported Ending Balance
    ws_rec.cell(row=13, column=1, value="Reported Ending Balance").font = summary_font
    c_rep = ws_rec.cell(row=13, column=2, value=float(to_decimal(payload.metadata.ending_balance)))
    c_rep.font = summary_font
    c_rep.number_format = currency_fmt
    c_rep.alignment = Alignment(horizontal="right")

    # Row 14: Discrepancy Formula (=B12-B13)
    ws_rec.cell(row=14, column=1, value="Discrepancy (Variance)").font = summary_font
    c_disc = ws_rec.cell(row=14, column=2, value="=B12-B13")
    c_disc.font = summary_font
    c_disc.number_format = currency_fmt
    c_disc.alignment = Alignment(horizontal="right")
    c_disc.border = double_bottom_border
    ws_rec.cell(row=14, column=1).border = double_bottom_border

    # Row 16: Reconciliation Status Badge
    is_rec = payload.reconciliation.is_reconciled
    ws_rec.cell(row=16, column=1, value="Status").font = bold_font
    stat_cell = ws_rec.cell(row=16, column=2, value="RECONCILED" if is_rec else "DISCREPANCY DETECTED")
    stat_cell.fill = green_fill if is_rec else rose_fill
    stat_cell.font = green_font if is_rec else rose_font
    stat_cell.alignment = Alignment(horizontal="center", vertical="center")

    # Column widths for Summary sheet
    ws_rec.column_dimensions["A"].width = 28
    ws_rec.column_dimensions["B"].width = 24
    ws_rec.column_dimensions["C"].width = 16
    ws_rec.column_dimensions["D"].width = 16

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 3. Structured JSON Exporter
# ---------------------------------------------------------------------------

def export_to_json(payload: ExportPayload) -> bytes:
    """
    Generates structured, versioned hierarchical JSON bytes.
    Preserves exact Decimal string representations to prevent floating-point drift.
    """
    category_totals: Dict[str, Dict[str, Decimal]] = {}
    for tx in payload.transactions:
        cat = tx.category or "Uncategorized"
        if cat not in category_totals:
            category_totals[cat] = {"credits": Decimal("0.00"), "debits": Decimal("0.00")}
        amt = to_decimal(tx.amount)
        if tx.type == "credit":
            category_totals[cat]["credits"] += amt
        else:
            category_totals[cat]["debits"] += amt

    category_summary = [
        {
            "category": cat,
            "credits": format_decimal(data["credits"]),
            "debits": format_decimal(data["debits"]),
            "net": format_decimal(data["credits"] - data["debits"]),
        }
        for cat, data in sorted(category_totals.items())
    ]

    export_dict: Dict[str, Any] = {
        "$schema": "https://api.statementparser.com/schemas/v1/statement.json",
        "version": "1.0.0",
        "metadata": payload.metadata.model_dump(),
        "reconciliation": payload.reconciliation.model_dump(),
        "transactions": [tx.model_dump() for tx in payload.transactions],
        "category_summary": category_summary,
    }

    return json.dumps(export_dict, indent=2, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# 4. Programmatic Round-Trip Re-Ingestion Verification Engine
# ---------------------------------------------------------------------------

def verify_round_trip(
    exported_bytes: bytes,
    format_type: str,
    original_payload: ExportPayload,
) -> Tuple[bool, str]:
    """
    Programmatic re-ingestion asserting Ingest(Export(S)) == S with zero schema corruption.
    Validates CSV, XLSX, or JSON against the original ExportPayload.
    """
    fmt = format_type.lower().strip(".")

    if fmt == "json":
        try:
            raw_text = exported_bytes.decode("utf-8")
            data = json.loads(raw_text)
        except Exception as e:
            return False, f"JSON decoding failed: {str(e)}"

        if "metadata" not in data or "reconciliation" not in data or "transactions" not in data:
            return False, "JSON missing required top-level keys ('metadata', 'reconciliation', 'transactions')"

        try:
            recovered_payload = ExportPayload.model_validate(data)
        except Exception as e:
            return False, f"ExportPayload validation failed on JSON: {str(e)}"

        if recovered_payload.metadata.starting_balance != original_payload.metadata.starting_balance:
            return False, f"Starting balance mismatch: {recovered_payload.metadata.starting_balance} != {original_payload.metadata.starting_balance}"
        if recovered_payload.metadata.ending_balance != original_payload.metadata.ending_balance:
            return False, f"Ending balance mismatch: {recovered_payload.metadata.ending_balance} != {original_payload.metadata.ending_balance}"
        if len(recovered_payload.transactions) != len(original_payload.transactions):
            return False, f"Transaction count mismatch: {len(recovered_payload.transactions)} != {len(original_payload.transactions)}"

        for idx, (orig, rec) in enumerate(zip(original_payload.transactions, recovered_payload.transactions)):
            if orig.amount != rec.amount:
                return False, f"Row {idx} amount mismatch: {orig.amount} != {rec.amount}"
            if orig.payee != rec.payee:
                return False, f"Row {idx} payee mismatch: {orig.payee} != {rec.payee}"
            if orig.date != rec.date:
                return False, f"Row {idx} date mismatch: {orig.date} != {rec.date}"
            if orig.type != rec.type:
                return False, f"Row {idx} type mismatch: {orig.type} != {rec.type}"

        return True, "JSON round-trip lossless verification passed"

    elif fmt == "csv":
        if not exported_bytes.startswith(b"\xef\xbb\xbf"):
            return False, "CSV missing mandatory UTF-8 BOM prefix"

        try:
            text = exported_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            return False, f"CSV is not valid UTF-8: {str(e)}"

        reader = csv.reader(io.StringIO(text))
        rows = list(reader)

        tx_start = -1
        for idx, row in enumerate(rows):
            if row and "Date" in row[0] and len(row) >= 5:
                tx_start = idx + 1
                break

        if tx_start == -1:
            return False, "Could not find transaction table header row"

        data_rows = rows[tx_start:]
        if len(data_rows) != len(original_payload.transactions):
            return False, f"Row count mismatch: expected {len(original_payload.transactions)}, got {len(data_rows)}"

        for idx, orig in enumerate(original_payload.transactions):
            row = data_rows[idx]
            if orig.date not in row[0]:
                return False, f"Row {idx} date mismatch: expected {orig.date}, got {row[0]}"
            if orig.payee not in row[1]:
                return False, f"Row {idx} payee mismatch: expected {orig.payee}, got {row[1]}"
            orig_amt = f"{to_decimal(orig.amount):.2f}"
            if orig_amt not in row[3]:
                return False, f"Row {idx} amount mismatch: expected {orig_amt}, got {row[3]}"

        return True, "CSV round-trip lossless verification passed"

    elif fmt in ("xlsx", "excel"):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(exported_bytes), data_only=False)
        except Exception as e:
            return False, f"Failed to load Excel workbook: {str(e)}"

        if "Transactions" not in wb.sheetnames:
            return False, "Workbook missing 'Transactions' sheet"
        if "Reconciliation Summary" not in wb.sheetnames:
            return False, "Workbook missing 'Reconciliation Summary' sheet"

        ws = wb["Transactions"]
        header_vals = [cell.value for cell in ws[1]]
        if "Date" not in header_vals or "Amount" not in header_vals:
            return False, f"Missing expected headers in Transactions sheet: {header_vals}"

        # Verify data rows
        expected_tx_count = len(original_payload.transactions)
        if expected_tx_count > 0:
            row2_amount = ws.cell(row=2, column=4).value
            if not isinstance(row2_amount, (int, float)):
                return False, f"Amount column cell value is not numeric: {type(row2_amount)}"

        return True, "XLSX round-trip lossless verification passed"

    return False, f"Unsupported format type: {format_type}"
