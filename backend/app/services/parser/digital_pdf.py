"""
Digital PDF Table & Metadata Extractor using pdfplumber and pypdf.

Features:
- Preserves table columns (Date, Description, Debits, Credits, Balance)
- Filters repeated headers/footers across multi-page statements
- Merges multi-line wrapped payee descriptions
- Filters 'Balance Brought Forward' / 'Carried Forward' pseudo-transactions
- Robust metadata extraction (Bank Name, Account, Period, Starting/Ending Balance)
- Line-by-line fallback when visual tables are unbordered
"""
import io
import re
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import pdfplumber
import pypdf

from app.schemas.statement import StatementMetadata
from app.schemas.transaction import TransactionRecord
from app.services.parser.normalizer import (
    clean_payee,
    classify_category,
    normalize_date,
    parse_amount,
)


KNOWN_BANKS = [
    "Chase",
    "JPMorgan Chase",
    "Bank of America",
    "Wells Fargo",
    "Citibank",
    "Citi",
    "Capital One",
    "Barclays",
    "HSBC",
    "Apex Global Commercial Bank",
    "PNC Bank",
    "TD Bank",
    "US Bank",
    "Truist",
    "Silicon Valley Bank",
    "First Republic Bank",
    "Monzo",
    "Revolut",
]


def extract_metadata_from_text(full_text: str, default_page_count: int = 1) -> StatementMetadata:
    """Extracts statement metadata from full document text."""
    # 1. Bank Name
    bank_name = "Unknown Bank"
    for bank in KNOWN_BANKS:
        if re.search(r"\b" + re.escape(bank) + r"\b", full_text, re.IGNORECASE):
            bank_name = bank
            break
    if bank_name == "Unknown Bank":
        # Look at the first 3 lines
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        if lines:
            first_line = lines[0]
            if len(first_line) < 50 and not re.search(r"statement|page|account", first_line, re.IGNORECASE):
                bank_name = first_line

    # 2. Account Number
    account_number = ""
    acct_match = re.search(
        r"(?:Account|Acct|A/C)(?:\s*(?:Number|No|#))?:?\s*([X\*\d]{4,20})",
        full_text,
        re.IGNORECASE,
    )
    if acct_match:
        account_number = acct_match.group(1).strip()

    # 3. Statement Period
    period_start = None
    period_end = None
    period_match = re.search(
        r"(?:Statement\s+Period|Billing\s+Cycle|Period\s+Covered|Date\s+Range|Period):?\s*"
        r"([A-Za-z0-9,/\-.\s]+?)\s+(?:to|through|-)\s+([A-Za-z0-9,/\-.\s]+)",
        full_text,
        re.IGNORECASE,
    )
    if period_match:
        raw_start = period_match.group(1).strip()
        raw_end = period_match.group(2).strip()
        # Clean line breaks
        raw_start = raw_start.split("\n")[0].strip()
        raw_end = raw_end.split("\n")[0].strip()
        period_start = normalize_date(raw_start)
        period_end = normalize_date(raw_end)

    if not period_start:
        period_start = datetime.now().strftime("%Y-%m-01")
    if not period_end:
        period_end = datetime.now().strftime("%Y-%m-%d")

    # 4. Starting Balance
    start_bal_str = "0.00"
    start_match = re.search(
        r"(?:Beginning|Starting|Opening|Previous)\s+Balance:?\s*"
        r"(\(?\s*[\$€£¥]?\s*-?\s*[\$€£¥]?\s*[\d.,]+(?:\s*[A-Za-z€£$¥]+)?\s*\)?)",
        full_text,
        re.IGNORECASE,
    )
    if start_match:
        raw_start = start_match.group(1).strip()
        amt, _ = parse_amount(raw_start)
        if amt is not None:
            is_neg = "-" in raw_start or ("(" in raw_start and ")" in raw_start)
            start_bal_str = f"-{amt}" if is_neg else amt

    # 5. Ending Balance
    end_bal_str = start_bal_str
    end_match = re.search(
        r"(?:Ending|Closing|New)\s+Balance:?\s*"
        r"(\(?\s*[\$€£¥]?\s*-?\s*[\$€£¥]?\s*[\d.,]+(?:\s*[A-Za-z€£$¥]+)?\s*\)?)",
        full_text,
        re.IGNORECASE,
    )
    if end_match:
        raw_end = end_match.group(1).strip()
        amt, _ = parse_amount(raw_end)
        if amt is not None:
            is_neg = "-" in raw_end or ("(" in raw_end and ")" in raw_end)
            end_bal_str = f"-{amt}" if is_neg else amt

    # 6. Currency
    currency = "USD"
    if "€" in full_text or "EUR" in full_text:
        currency = "EUR"
    elif "£" in full_text or "GBP" in full_text:
        currency = "GBP"
    elif "CAD" in full_text:
        currency = "CAD"
    elif "¥" in full_text or "JPY" in full_text:
        currency = "JPY"

    return StatementMetadata(
        bank_name=bank_name,
        account_number=account_number,
        statement_period_start=period_start,
        statement_period_end=period_end,
        starting_balance=start_bal_str,
        ending_balance=end_bal_str,
        currency=currency,
        page_count=default_page_count,
    )


def is_header_or_footer(line_str: str) -> bool:
    """Returns True if the line is a repeated header, footer, or column label."""
    s = line_str.lower().strip()
    if not s:
        return True
    if re.search(r"^page\s+\d+\s+of\s+\d+", s):
        return True
    if re.search(r"date.*(?:description|payee|particulars|details|txn|trans)?.*(?:type|amount|debit|credit|balance)", s):
        return True
    if re.search(r"balance\s+(brought|carried)\s+forward", s):
        return True
    return False


def parse_table_row_to_tx(
    row: List[Optional[str]],
    col_map: Dict[str, int],
    default_year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Parses a structured table row into a transaction dict."""
    date_idx = col_map.get("date")
    desc_idx = col_map.get("desc")
    type_idx = col_map.get("type")
    debit_idx = col_map.get("debit")
    credit_idx = col_map.get("credit")
    amt_idx = col_map.get("amount")
    bal_idx = col_map.get("balance")

    raw_date = row[date_idx].strip() if date_idx is not None and date_idx < len(row) and row[date_idx] else ""
    norm_date = normalize_date(raw_date, default_year=default_year)
    if not norm_date:
        return None

    raw_desc = row[desc_idx].strip() if desc_idx is not None and desc_idx < len(row) and row[desc_idx] else ""

    # Parse explicit type from Type column if available
    explicit_type: Optional[str] = None
    if type_idx is not None and type_idx < len(row) and row[type_idx]:
        raw_t = row[type_idx].strip().lower()
        if any(k in raw_t for k in ["credit", "deposit", "dep", "refund", "interest", "payroll", "addition"]) or raw_t in ["cr", "c", "+"]:
            explicit_type = "credit"
        elif any(k in raw_t for k in ["debit", "withdrawal", "payment", "pmt", "fee", "charge", "pos", "purchase", "chk", "check", "subtraction", "w/d"]) or raw_t in ["dr", "d", "-"]:
            explicit_type = "debit"

    # Amount and Type resolution
    tx_type = explicit_type or "debit"
    amount_str = None

    if debit_idx is not None and credit_idx is not None:
        # Separate columns for debit and credit
        deb_val = row[debit_idx].strip() if debit_idx < len(row) and row[debit_idx] else ""
        cred_val = row[credit_idx].strip() if credit_idx < len(row) and row[credit_idx] else ""

        if cred_val and re.search(r"\d", cred_val):
            parsed_amt, _ = parse_amount(cred_val, default_type="credit")
            if parsed_amt:
                amount_str = parsed_amt
                tx_type = "credit"
        elif deb_val and re.search(r"\d", deb_val):
            parsed_amt, _ = parse_amount(deb_val, default_type="debit")
            if parsed_amt:
                amount_str = parsed_amt
                tx_type = "debit"
    elif amt_idx is not None:
        amt_val = row[amt_idx].strip() if amt_idx < len(row) and row[amt_idx] else ""
        if amt_val and re.search(r"\d", amt_val):
            parsed_amt, inferred_type = parse_amount(amt_val)
            if parsed_amt:
                amount_str = parsed_amt
                tx_type = explicit_type or inferred_type or "debit"

    if not amount_str:
        return None

    # Balance
    running_bal_str = "0.00"
    if bal_idx is not None and bal_idx < len(row) and row[bal_idx]:
        b_val = row[bal_idx].strip()
        parsed_bal, _ = parse_amount(b_val)
        if parsed_bal:
            if "-" in b_val or (b_val.startswith("(") and b_val.endswith(")")):
                running_bal_str = f"-{parsed_bal}"
            else:
                running_bal_str = parsed_bal

    payee = clean_payee(raw_desc)
    category = classify_category(payee, raw_desc)

    return {
        "id": f"tx_{uuid.uuid4().hex[:8]}",
        "date": norm_date,
        "payee": payee,
        "raw_description": raw_desc,
        "type": tx_type,
        "amount": amount_str,
        "category": category,
        "running_balance": running_bal_str,
        "has_anomaly": False,
        "anomaly_type": None,
    }


def identify_columns(header_row: List[Optional[str]]) -> Dict[str, int]:
    """Identifies the indices of key columns from a header row."""
    col_map = {}
    for idx, cell in enumerate(header_row):
        if not cell:
            continue
        c = cell.lower().strip()
        if "date" in c:
            col_map["date"] = idx
        elif (
            any(k in c for k in ["txn type", "trans type", "transaction type", "cr/dr", "dr/cr", "d/c", "c/d", "credit/debit", "debit/credit"])
            or c == "type"
            or (len(c) <= 12 and "type" in c)
        ):
            col_map["type"] = idx
        elif any(k in c for k in ["description", "payee", "details", "narrative", "particulars", "memo", "transaction"]):
            col_map["desc"] = idx
        elif any(k in c for k in ["withdrawal", "debit", "subtraction", "payments"]) and not any(k in c for k in ["credit", "cr"]):
            col_map["debit"] = idx
        elif any(k in c for k in ["deposit", "credit", "addition"]) and not any(k in c for k in ["debit", "dr"]):
            col_map["credit"] = idx
        elif "amount" in c:
            col_map["amount"] = idx
        elif any(k in c for k in ["balance"]):
            col_map["balance"] = idx
    return col_map


def extract_transactions_from_text_fallback(
    text: str,
    default_year: Optional[int] = None,
    starting_balance: str = "0.00",
) -> List[TransactionRecord]:
    """
    Regex fallback extraction for digital PDFs where tables lack explicit lines.
    Looks for line patterns: Date Description [Debits] [Credits] Balance
    """
    records: List[TransactionRecord] = []
    lines = text.splitlines()

    current_bal = Decimal(starting_balance)

    # Date pattern at start of line
    date_regex = re.compile(
        r"^(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}(?:[-/.]\d{2,4})?|\d{1,2}-[A-Za-z]{3}(?:-\d{2,4})?|[A-Za-z]{3}\.?\s+\d{1,2}(?:,?\s+\d{4})?)\b"
    )

    current_tx: Optional[Dict[str, Any]] = None

    for line in lines:
        stripped = line.strip()
        if not stripped or is_header_or_footer(stripped):
            continue

        match = date_regex.match(stripped)
        if match:
            # Finalize previous transaction
            if current_tx:
                records.append(TransactionRecord(**current_tx))
                current_tx = None

            raw_date = match.group(1)
            norm_date = normalize_date(raw_date, default_year=default_year)
            remainder = stripped[match.end():].strip()

            # Find all currency/amount-like patterns in remainder
            # e.g., $1,250.00, -$45.00, (150.00), 50.00, 1.250,50 €
            amt_matches = list(re.finditer(r"(?:\$|\€|\£|\¥)?\s*\(?-?[\$€£¥]?\d+(?:[.,]\d{3})*(?:[.,]\d{2})?\)?(?:\s*(?:CR|DR|[€£$¥A-Za-z]{1,3}))?", remainder))

            if amt_matches:
                desc_part = remainder[: amt_matches[0].start()].strip()
                amounts = [m.group(0).strip() for m in amt_matches]

                # Determine amounts
                amt_str = None
                tx_type = "debit"
                bal_str = "0.00"

                if len(amounts) >= 3:
                    # Debit, Credit, Balance
                    deb_val = amounts[0]
                    cred_val = amounts[1]
                    bal_val = amounts[2]
                    p_bal, _ = parse_amount(bal_val)
                    if p_bal:
                        bal_str = p_bal

                    p_deb, _ = parse_amount(deb_val)
                    p_cred, _ = parse_amount(cred_val)
                    if p_cred and Decimal(p_cred) > 0:
                        amt_str = p_cred
                        tx_type = "credit"
                    elif p_deb and Decimal(p_deb) > 0:
                        amt_str = p_deb
                        tx_type = "debit"
                elif len(amounts) == 2:
                    # Amount, Balance
                    p_amt, inferred_type = parse_amount(amounts[0])
                    p_bal, _ = parse_amount(amounts[1])
                    if p_amt:
                        amt_str = p_amt
                        tx_type = inferred_type or "debit"
                    if p_bal:
                        bal_str = p_bal
                elif len(amounts) == 1:
                    p_amt, inferred_type = parse_amount(amounts[0])
                    if p_amt:
                        amt_str = p_amt
                        tx_type = inferred_type or "debit"
                    # Calculate running balance if not present
                    amt_dec = Decimal(amt_str or "0.00")
                    if tx_type == "credit":
                        current_bal += amt_dec
                    else:
                        current_bal -= amt_dec
                    bal_str = f"{current_bal:.2f}"

                if amt_str:
                    payee = clean_payee(desc_part)
                    category = classify_category(payee, desc_part)
                    current_tx = {
                        "id": f"tx_{uuid.uuid4().hex[:8]}",
                        "date": norm_date or datetime.now().strftime("%Y-%m-%d"),
                        "payee": payee,
                        "raw_description": desc_part,
                        "type": tx_type,
                        "amount": amt_str,
                        "category": category,
                        "running_balance": bal_str,
                        "has_anomaly": False,
                        "anomaly_type": None,
                    }
        else:
            # Wrapped description line
            if current_tx and stripped and not re.search(r"\$\d+\.\d{2}", stripped):
                current_tx["raw_description"] += " " + stripped
                current_tx["payee"] = clean_payee(current_tx["raw_description"])
                current_tx["category"] = classify_category(current_tx["payee"], current_tx["raw_description"])

    if current_tx:
        records.append(TransactionRecord(**current_tx))

    return records


def extract_digital_pdf(file_bytes: bytes) -> Tuple[StatementMetadata, List[TransactionRecord]]:
    """
    Primary digital PDF extraction function.
    Combines table parsing and text extraction with multi-line merging.
    """
    all_text = ""
    tables_data: List[List[List[Optional[str]]]] = []

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            t = page.extract_text() or ""
            all_text += t + "\n"
            tbls = page.extract_tables()
            if tbls:
                tables_data.extend(tbls)

    metadata = extract_metadata_from_text(all_text, default_page_count=page_count)

    # Derive year for date parsing
    default_year = None
    if metadata.statement_period_start:
        try:
            default_year = int(metadata.statement_period_start.split("-")[0])
        except Exception:
            pass

    records: List[TransactionRecord] = []

    # Try extracting from structured tables first
    if tables_data:
        active_col_map: Optional[Dict[str, int]] = None
        active_col_count: Optional[int] = None

        for table in tables_data:
            if not table or len(table) < 1:
                continue

            # Inspect the first row to determine if this table brings its own header
            first_row_cleaned = [c.replace("\n", " ").strip() if c else "" for c in table[0]]
            first_cand = identify_columns(first_row_cleaned)
            first_has_header = "date" in first_cand and (
                "amount" in first_cand or "debit" in first_cand or "credit" in first_cand
            )

            col_map: Dict[str, int] = {}
            if first_has_header:
                col_map = first_cand
                active_col_map = dict(col_map)
                active_col_count = len(first_row_cleaned)
            elif active_col_map is not None and len(table[0]) == active_col_count:
                # Inherit previous active col_map if table contains at least one parseable date
                date_col_idx = active_col_map.get("date", 0)
                has_date = any(
                    normalize_date(r[date_col_idx], default_year=default_year) is not None
                    for r in table
                    if len(r) > date_col_idx and r[date_col_idx]
                )
                if has_date:
                    col_map = dict(active_col_map)

            data_rows = []

            for row_idx, row in enumerate(table):
                # Clean row cells
                cleaned_row = [c.replace("\n", " ").strip() if c else "" for c in row]
                row_str = " ".join(cleaned_row)

                # Check if this row is a header, footer, or page divider
                if is_header_or_footer(row_str):
                    cand_map = identify_columns(cleaned_row)
                    if "date" in cand_map and ("amount" in cand_map or "debit" in cand_map or "credit" in cand_map):
                        col_map = cand_map
                        active_col_map = dict(col_map)
                        active_col_count = len(cleaned_row)
                    continue

                if not col_map:
                    # Check if an intermediate row acts as a header (e.g. following a table title)
                    cand_map = identify_columns(cleaned_row)
                    if "date" in cand_map and ("amount" in cand_map or "debit" in cand_map or "credit" in cand_map):
                        col_map = cand_map
                        active_col_map = dict(col_map)
                        active_col_count = len(cleaned_row)
                        continue
                    elif active_col_map is not None and len(cleaned_row) == active_col_count:
                        col_map = dict(active_col_map)

                # Multi-line merging in table rows:
                if col_map:
                    date_col = col_map.get("date", 0)
                    row_date = cleaned_row[date_col] if date_col < len(cleaned_row) else ""
                    if not normalize_date(row_date, default_year=default_year):
                        # wrapped row
                        desc_col = col_map.get("desc", 1)
                        if desc_col < len(cleaned_row) and cleaned_row[desc_col]:
                            wrap_text = cleaned_row[desc_col]
                            if data_rows:
                                data_rows[-1]["raw_description"] += " " + wrap_text
                                data_rows[-1]["payee"] = clean_payee(data_rows[-1]["raw_description"])
                                data_rows[-1]["category"] = classify_category(
                                    data_rows[-1]["payee"], data_rows[-1]["raw_description"]
                                )
                            elif records:
                                # Wrapped across table/page boundary
                                updated_desc = records[-1].raw_description + " " + wrap_text
                                updated_payee = clean_payee(updated_desc)
                                updated_cat = classify_category(updated_payee, updated_desc)
                                records[-1] = records[-1].model_copy(
                                    update={
                                        "raw_description": updated_desc,
                                        "payee": updated_payee,
                                        "category": updated_cat,
                                    }
                                )
                        continue

                    parsed_tx = parse_table_row_to_tx(cleaned_row, col_map, default_year=default_year)
                    if parsed_tx:
                        data_rows.append(parsed_tx)

            for d in data_rows:
                records.append(TransactionRecord(**d))

    # If table extraction yielded nothing, use the text fallback
    if not records:
        records = extract_transactions_from_text_fallback(
            all_text,
            default_year=default_year,
            starting_balance=metadata.starting_balance,
        )

    # If starting and ending balance were not in headers, infer from transactions
    if metadata.starting_balance == "0.00" and records:
        first_tx = records[0]
        # If first tx has a running balance, we can derive start balance
        if first_tx.running_balance and first_tx.running_balance != "0.00":
            first_amt = Decimal(first_tx.amount)
            first_run = Decimal(first_tx.running_balance)
            derived_start = first_run - first_amt if first_tx.type == "credit" else first_run + first_amt
            metadata.starting_balance = f"{derived_start:.2f}"

    if metadata.ending_balance == "0.00" and records:
        last_tx = records[-1]
        if last_tx.running_balance and last_tx.running_balance != "0.00":
            metadata.ending_balance = last_tx.running_balance

    return metadata, records
