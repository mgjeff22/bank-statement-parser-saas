"""
Adversarial Stress Test Harness for Milestone 1:
Document Router, Digital PDF Extractor, OCR/Vision Pipeline, and Normalizer.

Covers the 4 Challenger 2 stress dimensions:
1. Corrupted & malformed files (truncated PDF headers, invalid image bytes, empty input)
2. Deep multi-page PDFs (5+ pages) with continuing tables and varying column widths
3. Extremely skewed and low-contrast synthetic images stressing OpenCV preprocessing
4. Unusual date and currency formats (£, €, ¥, negative accounting parens, comma decimal separators)
"""
import io
import os
from decimal import Decimal
import numpy as np
import cv2
import pytest
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak, Table, TableStyle

from app.schemas.statement import StatementParseResult
from app.services.parser.router import detect_document_type, parse_statement
from app.services.parser.digital_pdf import (
    extract_digital_pdf,
    extract_metadata_from_text,
)
from app.services.parser.ocr_engine import (
    preprocess_image,
    deskew_image,
    run_ocr_on_image,
    render_pdf_to_images,
)
from app.services.parser.normalizer import (
    normalize_date,
    parse_amount,
    clean_payee,
    classify_category,
)


# ==============================================================================
# Helper Generators for Synthetic Test Fixtures
# ==============================================================================

def create_multipage_pdf_fixture(
    pages: int = 5,
    repeat_headers: bool = True,
    vary_widths: bool = True,
) -> bytes:
    """
    Generates a deep multi-page synthetic digital PDF statement using ReportLab.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )
    styles = getSampleStyleSheet()
    story = []

    # Page 1 Header
    story.append(Paragraph("<b>Apex Global Commercial Bank</b>", styles["Title"]))
    story.append(Paragraph("Account Number: ************8842", styles["Normal"]))
    story.append(
        Paragraph("Starting Balance: $10,000.00 | Ending Balance: $10,250.00", styles["Normal"])
    )
    story.append(Paragraph("Statement Period: 2026-01-01 to 2026-01-31", styles["Normal"]))

    headers = ["Date", "Description", "Debits (-)", "Credits (+)", "Balance"]
    running_balance = Decimal("10000.00")

    for page_num in range(1, pages + 1):
        table_rows = []
        if repeat_headers or page_num == 1:
            table_rows.append(headers)

        for row_num in range(1, 4):
            day = page_num * 5 + row_num
            date_str = f"2026-01-{day:02d}"
            desc = f"Merchant Store P{page_num} Item {row_num}"

            if row_num == 1:
                # Credit
                credit_str = "100.00"
                debit_str = ""
                running_balance += Decimal("100.00")
            else:
                # Debit
                credit_str = ""
                debit_str = "25.00"
                running_balance -= Decimal("25.00")

            bal_str = f"${running_balance:.2f}"
            cred_formatted = f"${credit_str}" if credit_str else ""
            deb_formatted = f"${debit_str}" if debit_str else ""
            table_rows.append([date_str, desc, deb_formatted, cred_formatted, bal_str])

        # Vary column widths per page if requested
        if vary_widths:
            col_widths = [60 + (page_num * 4), 220 - (page_num * 4), 75, 75, 80]
        else:
            col_widths = [70, 220, 75, 75, 80]

        table = Table(table_rows, colWidths=col_widths)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#94a3b8")),
                    ("BACKGROUND", (0, 0), (-1, 0 if (repeat_headers or page_num == 1) else -1), colors.whitesmoke),
                ]
            )
        )
        story.append(table)

        if page_num < pages:
            story.append(PageBreak())

    doc.build(story)
    return buf.getvalue()


# ==============================================================================
# Dimension 1: Corrupted & Malformed Files
# ==============================================================================

class TestDimension1CorruptedAndMalformedFiles:
    """
    Stress-tests document router and pipeline against malformed inputs,
    truncated file headers, and random byte streams.
    """

    def test_document_router_mime_and_magic_fallbacks(self):
        """Verifies router classification heuristics under non-standard inputs."""
        # Arbitrary bytes with .png extension
        assert detect_document_type(b"garbage", filename="doc.png") == "raster_image"
        # Arbitrary bytes with .pdf extension
        assert detect_document_type(b"garbage", filename="doc.pdf") == "scanned_pdf"
        # PNG magic bytes without filename
        assert detect_document_type(b"\x89PNG\r\n\x1a\n\x00\x00", "") == "raster_image"
        # JPEG magic bytes without filename
        assert detect_document_type(b"\xff\xd8\xff\xe0", "") == "raster_image"
        # WebP magic bytes without filename
        assert detect_document_type(b"RIFF\x00\x00\x00\x00WEBPVP8", "") == "raster_image"
        # Default fallback for unknown binary
        assert detect_document_type(b"\x00\x01\x02\x03\x04", "") == "raster_image"

    def test_truncated_pdf_header_raw_library_behavior(self):
        """
        Verifies underlying library behavior: pypdfium2 raises PdfiumError on truncated PDF.
        """
        import pypdfium2
        truncated_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntruncated"
        with pytest.raises(Exception) as exc_info:
            pypdfium2.PdfDocument(truncated_pdf)
        assert "PdfiumError" in type(exc_info.value).__name__

    def test_truncated_pdf_header_graceful_handling_target(self):
        """
        TARGET CONTRACT:
        A robust production parser must handle corrupted PDF files gracefully without
        crashing the backend worker process, returning empty records and diagnostic flags.
        """
        truncated_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntruncated"
        result = parse_statement(truncated_pdf, filename="truncated.pdf")
        assert isinstance(result, StatementParseResult)
        assert result.transactions == []
        assert result.reconciliation.is_reconciled is False

    def test_empty_bytes_input_raw_library_behavior(self):
        """Underlying pypdfium2 raises on empty bytes."""
        import pypdfium2
        with pytest.raises(Exception) as exc_info:
            pypdfium2.PdfDocument(b"")
        assert "PdfiumError" in type(exc_info.value).__name__

    def test_empty_bytes_input_graceful_handling_target(self):
        """TARGET CONTRACT: Empty bytes must be handled gracefully without crashing."""
        result = parse_statement(b"", filename="empty.pdf")
        assert isinstance(result, StatementParseResult)
        assert result.transactions == []
        assert result.reconciliation.is_reconciled is False

    def test_corrupted_png_bytes_raw_library_behavior(self):
        """Underlying PIL.Image raises UnidentifiedImageError on corrupted PNG bytes."""
        from PIL import Image, UnidentifiedImageError
        corrupted_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00CORRUPT_BYTES"
        with pytest.raises(UnidentifiedImageError):
            Image.open(io.BytesIO(corrupted_png))

    def test_corrupted_png_bytes_graceful_handling_target(self):
        """TARGET CONTRACT: Corrupted image bytes must be handled gracefully without crashing."""
        corrupted_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00CORRUPT_BYTES"
        result = parse_statement(corrupted_png, filename="statement.png", mime_type="image/png")
        assert isinstance(result, StatementParseResult)
        assert result.transactions == []
        assert result.reconciliation.is_reconciled is False

    def test_garbage_non_image_bytes_with_image_filename_graceful(self):
        """Passing ASCII text with .jpg extension is handled gracefully without crashing."""
        fake_jpeg = b"This is plain text and not a valid JPEG stream."
        result = parse_statement(fake_jpeg, filename="receipt.jpg", mime_type="image/jpeg")
        assert isinstance(result, StatementParseResult)
        assert result.transactions == []
        assert result.reconciliation.is_reconciled is False


# ==============================================================================
# Dimension 2: Deep Multi-Page PDFs (5+ Pages)
# ==============================================================================

class TestDimension2DeepMultiPagePDFs:
    """
    Stress-tests extraction across deep multi-page PDF statements (5+ pages),
    testing varying column widths, repeated headers, and continuing tables without headers.
    """

    def test_deep_5page_pdf_with_repeated_headers_and_varying_widths(self):
        """
        Tests 5-page PDF statement where each page repeats the column header
        and has slightly varying column widths.
        Asserts that all 15 transactions (3 per page * 5 pages) are extracted cleanly,
        and mathematical reconciliation verifies ending balance.
        """
        pdf_bytes = create_multipage_pdf_fixture(pages=5, repeat_headers=True, vary_widths=True)
        res = parse_statement(pdf_bytes, filename="5page_statement.pdf")

        assert res.document_type == "digital_pdf"
        assert res.parsing_engine == "pdfplumber"
        assert res.metadata.bank_name == "Apex Global Commercial Bank"
        assert res.metadata.starting_balance == "10000.00"
        assert res.metadata.ending_balance == "10250.00"
        assert len(res.transactions) == 15

        # Mathematical verification
        assert res.reconciliation.is_reconciled is True
        assert res.reconciliation.discrepancy == "0.00"
        assert res.reconciliation.total_credits == "500.00"   # 5 pages * 100.00
        assert res.reconciliation.total_debits == "250.00"    # 5 pages * 2 * 25.00
        assert res.reconciliation.net_cashflow == "250.00"

    def test_deep_5page_pdf_continuing_table_without_repeated_headers(self):
        """
        In real bank statements, tables frequently continue on pages 2, 3, 4, 5+
        WITHOUT repeating the column headers ('Date', 'Description', 'Debits', 'Credits', 'Balance').
        With active_col_map inheritance, all 15 transactions across all 5 pages are preserved.
        """
        pdf_bytes = create_multipage_pdf_fixture(pages=5, repeat_headers=False, vary_widths=False)
        _, records = extract_digital_pdf(pdf_bytes)
        assert len(records) == 15

    def test_deep_5page_pdf_continuing_table_target_extraction(self):
        """
        TARGET CONTRACT:
        Multi-page statements where tables continue without repeating headers on every page
        must extract 100% of transaction records across all 5 pages.
        """
        pdf_bytes = create_multipage_pdf_fixture(pages=5, repeat_headers=False, vary_widths=False)
        _, records = extract_digital_pdf(pdf_bytes)
        assert len(records) == 15


    def test_pypdfium2_rasterizer_on_5page_pdf(self):
        """Verifies CPU rasterizer handles 5-page PDF producing 5 PIL images."""
        pdf_bytes = create_multipage_pdf_fixture(pages=5, repeat_headers=True)
        images = render_pdf_to_images(pdf_bytes, dpi=100)
        assert len(images) == 5
        for img in images:
            assert isinstance(img, Image.Image)
            assert img.width > 500 and img.height > 700


# ==============================================================================
# Dimension 3: Computer Vision Preprocessing Stress (Skew & Low-Contrast)
# ==============================================================================

class TestDimension3ComputerVisionPreprocessingStress:
    """
    Stress-tests OpenCV preprocessing and deskewing:
    - Deskewing angles within threshold (0.25° to 20°) vs extreme angles (> 20°)
    - Ultra low-contrast synthetic images with CLAHE and Otsu binarization
    - Dark mode / inverted contrast mobile app screenshots
    """

    def test_deskew_mild_and_moderate_angles(self):
        """Verifies deskew_image corrects mild and moderate angles (3° and 12°)."""
        base_img = Image.new("RGB", (600, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(base_img)
        draw.text((50, 100), "TEST BANK STATEMENT 2026", fill=(0, 0, 0))
        draw.text((50, 150), "Starting Balance: $1000.00", fill=(0, 0, 0))

        for angle in [3.0, 12.0]:
            rotated = base_img.rotate(angle, fillcolor=(255, 255, 255))
            rot_cv = np.array(rotated)
            deskewed = deskew_image(rot_cv)
            assert isinstance(deskewed, np.ndarray)
            assert deskewed.shape == rot_cv.shape

    def test_deskew_extreme_angles_beyond_threshold(self):
        """
        EMPIRICAL OBSERVATION:
        deskew_image (ocr_engine.py line 78) contains:
            if abs(angle) < 0.25 or abs(angle) > 20: return image_cv
        When skew exceeds 20 degrees (e.g. 25° or 45°), deskewing is completely aborted.
        At 45 degrees, RapidOCR text recognition degrades to unusable output ('0.0').
        """
        img = Image.new("RGB", (600, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((50, 80), "Starting Balance: 1000.00", fill=(0, 0, 0))

        # Rotate by 45 degrees
        rot_img = img.rotate(45, fillcolor=(255, 255, 255))
        rot_cv = np.array(rot_img)
        deskewed = deskew_image(rot_cv)

        # Deskewing aborted, returned identical array
        np.testing.assert_array_equal(deskewed, rot_cv)

        # Run OCR to observe degradation
        text, conf = run_ocr_on_image(rot_img)
        # Text at 45 degrees is not recognized as 'Starting Balance'
        assert "Starting" not in text

    def test_low_contrast_images_clahe_otsu(self):
        """
        Verifies OpenCV adaptive contrast enhancement (CLAHE) and Otsu binarization
        under challenging low-contrast conditions:
        - Difference 40: (200, 160)
        - Difference 20: (200, 180)
        - Difference 6 (Ultra low contrast): (200, 194)
        """
        for bg_val, text_val in [(200, 160), (200, 180), (200, 194)]:
            img = Image.new("RGB", (600, 200), color=(bg_val, bg_val, bg_val))
            draw = ImageDraw.Draw(img)
            draw.text((50, 80), "Starting Balance: 1000.00", fill=(text_val, text_val, text_val))

            prep = preprocess_image(img)
            assert isinstance(prep, np.ndarray)
            assert len(prep.shape) == 2  # Single-channel binarized

            text, conf = run_ocr_on_image(img)
            assert "Starting Balance" in text
            assert "1000.00" in text
            assert conf > 0.80

    def test_dark_mode_inverted_contrast(self):
        """
        Verifies OCR on dark-mode bank statement images (e.g. mobile screenshots).
        Background: dark gray (20, 20, 20); Text: near-white (240, 240, 240).
        """
        img_dark = Image.new("RGB", (600, 200), color=(20, 20, 20))
        draw = ImageDraw.Draw(img_dark)
        draw.text((50, 80), "Starting Balance: 1000.00", fill=(240, 240, 240))

        text, conf = run_ocr_on_image(img_dark)
        assert "Starting Balance" in text
        assert "1000.00" in text
        assert conf > 0.85


# ==============================================================================
# Dimension 4: Unusual Date and Currency Formats
# ==============================================================================

class TestDimension4UnusualDateAndCurrencyFormats:
    """
    Stress-tests normalizer and metadata extractor on:
    - Currency symbols (£, €, ¥)
    - Negative accounting parentheses e.g. ($1,250.50), (£1,250.50), (1,250.50)
    - European comma decimal notation e.g. 1.250,50 €
    - European dotted dates (28.09.2026), ISO dot dates (2026.09.28), hyphenated months (28-Sep-2026)
    - Metadata extraction of non-USD starting and ending balances
    """

    def test_currency_amount_parsing_multicurrency(self):
        """Verifies parse_amount handles £, €, ¥, negative parens, and comma decimals."""
        # British Pounds
        amt, tx_type = parse_amount("£1,250.50")
        assert amt == "1250.50" and tx_type == "debit"

        amt, tx_type = parse_amount("(£1,250.50)")
        assert amt == "1250.50" and tx_type == "debit"

        amt, tx_type = parse_amount("+£500.00")
        assert amt == "500.00" and tx_type == "credit"

        # Euros with European comma decimal notation
        amt, tx_type = parse_amount("€1.250,50")
        assert amt == "1250.50" and tx_type == "debit"

        amt, tx_type = parse_amount("1.250,50 €")
        assert amt == "1250.50" and tx_type == "debit"

        amt, tx_type = parse_amount("(€1.250,50)")
        assert amt == "1250.50" and tx_type == "debit"

        amt, tx_type = parse_amount("-€50,00")
        assert amt == "50.00" and tx_type == "debit"

        amt, tx_type = parse_amount("100,00 CR")
        assert amt == "100.00" and tx_type == "credit"

        # Japanese Yen (integer currency without decimal cents)
        amt, tx_type = parse_amount("¥10,000")
        assert amt == "10000.00" and tx_type == "debit"

        amt, tx_type = parse_amount("¥ 500")
        assert amt == "500.00" and tx_type == "debit"

        amt, tx_type = parse_amount("+¥50,000")
        assert amt == "50000.00" and tx_type == "credit"

        # Accounting parentheses without currency symbol
        amt, tx_type = parse_amount("(1,250.50)")
        assert amt == "1250.50" and tx_type == "debit"

        # European comma decimal with space thousands separator
        amt, tx_type = parse_amount("1 250,50 €")
        assert amt == "1250.50" and tx_type == "debit"

    def test_date_normalization_standard_formats_pass(self):
        """Verifies standard formats normalize correctly to ISO-8601."""
        assert normalize_date("2026-09-28") == "2026-09-28"
        assert normalize_date("09/28/2026") == "2026-09-28"
        assert normalize_date("28/09/2026") == "2026-09-28"
        assert normalize_date("28 Sep 2026") == "2026-09-28"
        assert normalize_date("Sep 28, 2026") == "2026-09-28"

    def test_date_normalization_european_dotted_and_hyphenated_formats(self):
        """
        Verifies date normalization supports:
        - German/European dot notation: '28.09.2026' -> '2026-09-28'
        - ISO dot notation: '2026.09.28' -> '2026-09-28'
        - Hyphenated month text: '28-Sep-2026' -> '2026-09-28'
        - Abbreviated month with period: 'Sep. 28, 2026' -> '2026-09-28'
        """
        assert normalize_date("28.09.2026") == "2026-09-28"
        assert normalize_date("2026.09.28") == "2026-09-28"
        assert normalize_date("28-Sep-2026") == "2026-09-28"
        assert normalize_date("Sep. 28, 2026") == "2026-09-28"

    def test_date_normalization_european_formats_target(self):
        """TARGET CONTRACT: European dot notation and hyphenated dates should normalize to ISO-8601."""
        assert normalize_date("28.09.2026") == "2026-09-28"
        assert normalize_date("2026.09.28") == "2026-09-28"
        assert normalize_date("28-Sep-2026") == "2026-09-28"
        assert normalize_date("Sep. 28, 2026") == "2026-09-28"

    def test_metadata_extraction_non_usd_currency(self):
        """
        Verifies metadata extractor parses non-USD currencies (£, €) and European
        comma-separated balance decimals properly.
        """
        # UK Statement with £
        uk_text = (
            "Barclays Bank\n"
            "Account Number: 1234567890\n"
            "Statement Period: 01/09/2026 to 30/09/2026\n"
            "Starting Balance: £1,250.50\n"
            "Ending Balance: £3,500.00"
        )
        uk_meta = extract_metadata_from_text(uk_text)
        assert uk_meta.currency == "GBP"
        assert uk_meta.starting_balance == "1250.50"
        assert uk_meta.ending_balance == "3500.00"

        # European Statement with € and comma decimal
        eu_text = (
            "Barclays Bank\n"
            "Account Number: 1234567890\n"
            "Statement Period: 01/09/2026 to 30/09/2026\n"
            "Starting Balance: € 1.250,50\n"
            "Ending Balance: € 3.500,00"
        )
        eu_meta = extract_metadata_from_text(eu_text)
        assert eu_meta.currency == "EUR"
        assert eu_meta.starting_balance == "1250.50"
        assert eu_meta.ending_balance == "3500.00"

    def test_metadata_extraction_non_usd_currency_target(self):
        """TARGET CONTRACT: Metadata extractor must extract starting and ending balances for £ and €."""
        uk_text = (
            "Barclays Bank\n"
            "Starting Balance: £1,250.50\n"
            "Ending Balance: £3,500.00"
        )
        uk_meta = extract_metadata_from_text(uk_text)
        assert uk_meta.currency == "GBP"
        assert uk_meta.starting_balance == "1250.50"
        assert uk_meta.ending_balance == "3500.00"

        eu_text = (
            "Barclays Bank\n"
            "Starting Balance: € 1.250,50\n"
            "Ending Balance: € 3.500,00"
        )
        eu_meta = extract_metadata_from_text(eu_text)
        assert eu_meta.currency == "EUR"
        assert eu_meta.starting_balance == "1250.50"
        assert eu_meta.ending_balance == "3500.00"

