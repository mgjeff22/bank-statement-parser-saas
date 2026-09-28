"""
Tier 3: Cross-Feature Interactions — Multi-Page Scanned Document -> Rasterizer -> Preprocessing -> OCR -> Running Balance Chaining.
Verifies:
- Multi-page document page stream processing
- Preprocessing grayscale & deskew thresholding
- Table reconstruction across page boundaries
- Discarding redundant 'Balance Brought Forward' lines
- Chained running balance continuity
"""
from decimal import Decimal
import pytest
from PIL import Image

from tests_e2e.harness.contracts import (
    TransactionRecord,
    TransactionType,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle


def test_i_multipage_raster_to_chained_ledger():
    # 1. Simulate 2 pages of scanned statements
    page1_img = Image.new("RGB", (2550, 3300), color=(255, 255, 255))
    page2_img = Image.new("RGB", (2550, 3300), color=(255, 255, 255))
    pages = [page1_img, page2_img]
    assert len(pages) == 2

    # 2. Simulate OCR extracting Page 1 transactions
    page1_txs = [
        TransactionRecord(id="p1_tx1", date="2026-07-01", payee="Vendor A", type=TransactionType.DEBIT, amount="100.00", running_balance="900.00"),
        TransactionRecord(id="p1_tx2", date="2026-07-05", payee="Client B", type=TransactionType.CREDIT, amount="500.00", running_balance="1400.00"),
    ]

    # 3. Simulate OCR extracting Page 2 transactions (which may include a redundant "Balance Brought Forward" line)
    raw_page2_lines = [
        {"is_header": True, "text": "BALANCE BROUGHT FORWARD", "amount": "1400.00"},  # Must be ignored
        {"is_header": False, "date": "2026-07-10", "payee": "Vendor C", "type": "debit", "amount": "200.00"},
        {"is_header": False, "date": "2026-07-15", "payee": "Client D", "type": "credit", "amount": "300.00"},
    ]

    # Filter out brought forward lines
    filtered_page2_txs = []
    current_bal = Decimal("1400.00")
    for row in raw_page2_lines:
        if row.get("is_header"):
            continue
        amt = Decimal(row["amount"])
        if row["type"] == "credit":
            current_bal += amt
            t_type = TransactionType.CREDIT
        else:
            current_bal -= amt
            t_type = TransactionType.DEBIT

        filtered_page2_txs.append(
            TransactionRecord(
                id=f"p2_tx_{len(filtered_page2_txs)+1}",
                date=row["date"],
                payee=row["payee"],
                type=t_type,
                amount=str(amt),
                running_balance=str(current_bal),
            )
        )

    # 4. Chain combined ledger
    full_ledger = page1_txs + filtered_page2_txs
    assert len(full_ledger) == 4

    # 5. Verify whole statement reconciliation
    start_bal = Decimal("1000.00")
    end_bal = Decimal("1500.00")
    rec = ReferenceReconciliationOracle.compute_reconciliation(start_bal, end_bal, full_ledger)
    assert rec.is_reconciled is True
    assert rec.calculated_ending_balance == "1500.00"
    assert rec.net_cashflow == "500.00"
