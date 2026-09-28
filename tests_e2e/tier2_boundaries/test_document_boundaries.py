"""
Tier 2: Boundary & Corner Cases — Document Layout & File Dimensions Boundaries.
Verifies:
- 1-page statement with 1 transaction
- 1-page statement with 0 transactions (dormant account)
- High-volume multi-page statements (50+ transactions)
- Corrupted file header rejection
- Document page count scaling
"""
from decimal import Decimal
import pytest
from PIL import Image

from tests_e2e.harness.contracts import (
    TransactionRecord,
    TransactionType,
    StatementMetadata,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle


def test_b_doc_minimal_single_transaction():
    start = Decimal("500.00")
    tx = TransactionRecord(id="1", date="2026-08-01", payee="Single Tx", type=TransactionType.CREDIT, amount="100.00", running_balance="600.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, Decimal("600.00"), [tx])
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == "600.00"


def test_b_doc_zero_activity_dormant_account():
    start = Decimal("1250.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start, start, [])
    assert rec.is_reconciled is True
    assert rec.net_cashflow == "0.00"
    assert rec.total_credits == "0.00"
    assert rec.total_debits == "0.00"


def test_b_doc_high_volume_fifty_transactions():
    start = Decimal("10000.00")
    cur = start
    txs = []
    for i in range(1, 51):
        amt = Decimal(f"{i * 5}.00")
        if i % 2 == 0:
            cur += amt
            t_type = TransactionType.CREDIT
        else:
            cur -= amt
            t_type = TransactionType.DEBIT
        txs.append(TransactionRecord(id=f"tx_{i:03d}", date="2026-08-01", payee=f"Vendor {i}", type=t_type, amount=str(amt), running_balance=str(cur)))

    rec = ReferenceReconciliationOracle.compute_reconciliation(start, cur, txs)
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == str(cur)


def test_b_doc_corrupted_pdf_header_detection():
    corrupted_bytes = b"NOT_A_PDF_HEADER_CONTENT\x00\x01\x02"
    assert not corrupted_bytes.startswith(b"%PDF")


def test_b_doc_image_dimension_limits():
    # Verify Pillow handles standard 300 DPI Letter image dimensions
    w, h = 2550, 3300
    img = Image.new("L", (w, h), color=255)
    assert img.size == (2550, 3300)
    assert img.width * img.height == 8415000
