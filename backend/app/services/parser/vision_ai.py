"""
Multimodal Vision AI Extractor using Gemini 2.0 Flash via google-genai SDK.

Used as an intelligent fallback for heavily degraded, handwritten, or complex
multi-column bank statements when GEMINI_API_KEY is configured in the environment.
"""
import json
import os
import uuid
from typing import List, Optional, Tuple

from app.schemas.statement import StatementMetadata
from app.schemas.transaction import TransactionRecord
from app.services.parser.normalizer import clean_payee, classify_category, normalize_date, parse_amount


EXTRACTION_PROMPT = """
You are an expert financial document extraction engine.
Analyze this bank statement image or PDF document and extract structured JSON matching this schema:

{
  "metadata": {
    "bank_name": "string (e.g. Chase, Bank of America, Apex Global Commercial Bank)",
    "account_number": "string (e.g. ************8842 or 12345678)",
    "statement_period_start": "YYYY-MM-DD",
    "statement_period_end": "YYYY-MM-DD",
    "starting_balance": "decimal string e.g. 2500.00",
    "ending_balance": "decimal string e.g. 4500.00",
    "currency": "USD (or EUR, GBP, CAD)"
  },
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "payee": "Merchant or payee name",
      "type": "debit or credit",
      "amount": "positive decimal string e.g. 142.50",
      "running_balance": "decimal string e.g. 2357.50",
      "raw_description": "original description"
    }
  ]
}

Ensure all numbers are formatted as exact positive decimal strings with two decimal places.
All dates must be normalized to ISO-8601 YYYY-MM-DD.
"""


def is_gemini_available() -> bool:
    """Checks whether GEMINI_API_KEY is configured in the environment."""
    return bool(os.environ.get("GEMINI_API_KEY"))


def extract_with_gemini_vision(
    file_bytes: bytes,
    mime_type: str = "application/pdf",
) -> Optional[Tuple[StatementMetadata, List[TransactionRecord]]]:
    """
    Calls Gemini 2.0 Flash to extract structured bank statement metadata and transactions.
    Returns (StatementMetadata, list of TransactionRecord) or None if unavailable / failed.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[part, EXTRACTION_PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        if not response or not response.text:
            return None

        data = json.loads(response.text)
        meta_dict = data.get("metadata", {})
        txs_list = data.get("transactions", [])

        # Build StatementMetadata
        metadata = StatementMetadata(
            bank_name=meta_dict.get("bank_name") or "Unknown Bank",
            account_number=meta_dict.get("account_number") or "",
            statement_period_start=normalize_date(meta_dict.get("statement_period_start")) or "2026-01-01",
            statement_period_end=normalize_date(meta_dict.get("statement_period_end")) or "2026-01-31",
            starting_balance=parse_amount(meta_dict.get("starting_balance"))[0] or "0.00",
            ending_balance=parse_amount(meta_dict.get("ending_balance"))[0] or "0.00",
            currency=meta_dict.get("currency") or "USD",
        )

        transactions: List[TransactionRecord] = []
        for item in txs_list:
            raw_amt = str(item.get("amount", "0.00"))
            amt_str, _ = parse_amount(raw_amt)
            tx_type = item.get("type", "debit").lower()
            if tx_type not in ["debit", "credit"]:
                tx_type = "debit"

            raw_bal = str(item.get("running_balance", "0.00"))
            bal_str, _ = parse_amount(raw_bal)

            date_val = normalize_date(item.get("date")) or metadata.statement_period_start
            raw_desc = item.get("raw_description") or item.get("payee") or "Unknown"
            payee = clean_payee(item.get("payee") or raw_desc)
            category = classify_category(payee, raw_desc)

            tx = TransactionRecord(
                id=f"tx_{uuid.uuid4().hex[:8]}",
                date=date_val,
                payee=payee,
                raw_description=raw_desc,
                type=tx_type,
                amount=amt_str or "0.00",
                category=category,
                running_balance=bal_str or "0.00",
                has_anomaly=False,
                anomaly_type=None,
            )
            transactions.append(tx)

        return metadata, transactions

    except Exception:
        # Graceful degradation to local OCR on any network/API failure
        return None
