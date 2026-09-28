"""
Comprehensive Tests for Multimodal Statement Parsing Pipeline.

Verifies:
1. Date Normalizer (ISO-8601, US, UK, text months, year derivation)
2. Amount Parser (currencies, commas, parens, CR/DR, signs, European decimals)
3. Merchant / Payee Cleaner & Category Classifier
4. Document Router & Type Classifier (digital PDF, scanned PDF, raster image)
5. Computer Vision Preprocessing (CLAHE, deskewing, binarization)
6. Digital PDF Extraction with Table Extraction & Multi-line Merging
7. Scanned Image & PDF Rasterization / Local RapidOCR
8. Full End-to-End parse_statement Integration Test
"""
import io
import json
import os
from decimal import Decimal
import numpy as np
import cv2
import pytest
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

from app.schemas.statement import StatementParseResult
from app.services.parser.normalizer import (
    clean_payee,
    classify_category,
    normalize_date,
    parse_amount,
)
from app.services.parser.router import detect_document_type, parse_statement
from app.services.parser.digital_pdf import extract_digital_pdf
from app.services.parser.ocr_engine import (
    preprocess_image,
    deskew_image,
    render_pdf_to_images,
    run_ocr_on_image,
    extract_scanned_or_image,
)


class TestNormalizer:
    def test_normalize_date_formats(self):
        assert normalize_date("2026-09-14") == "2026-09-14"
        assert normalize_date("09/14/2026") == "2026-09-14"
        assert normalize_date("09-14-2026") == "2026-09-14"
        assert normalize_date("14/09/2026") == "2026-09-14"
        assert normalize_date("Sep 14, 2026") == "2026-09-14"
        assert normalize_date("14 Sep 2026") == "2026-09-14"
        assert normalize_date("September 14 2026") == "2026-09-14"
        assert normalize_date("09/14", default_year=2026) == "2026-09-14"
        assert normalize_date("Sep 14", default_year=2026) == "2026-09-14"
        assert normalize_date("") is None
        assert normalize_date("invalid date") is None

    def test_parse_amount_variations(self):
        # Clean currency
        amt, tx_type = parse_amount("$1,250.50")
        assert amt == "1250.50"
        assert tx_type == "debit"

        # Explicit negative / parens
        amt, tx_type = parse_amount("($150.00)")
        assert amt == "150.00"
        assert tx_type == "debit"

        amt, tx_type = parse_amount("-$45.20")
        assert amt == "45.20"
        assert tx_type == "debit"

        # Explicit credit / deposit
        amt, tx_type = parse_amount("+$1,500.00")
        assert amt == "1500.00"
        assert tx_type == "credit"

        # DR / CR notations
        amt, tx_type = parse_amount("120.00 CR")
        assert amt == "120.00"
        assert tx_type == "credit"

        amt, tx_type = parse_amount("75.50 DR")
        assert amt == "75.50"
        assert tx_type == "debit"

        # European format (1.250,50 €)
        amt, tx_type = parse_amount("1.250,50 €")
        assert amt == "1250.50"

        # European with single comma (150,50)
        amt, tx_type = parse_amount("150,50")
        assert amt == "150.50"

    def test_clean_payee_noise_removal(self):
        assert clean_payee("POS DEBIT 4821 WHOLE FOODS MARKET") == "Whole Foods Market"
        assert clean_payee("PURCHASE AUTHORIZED ON 09/14 SQ *BLUE BOTTLE COFFEE") == "Blue Bottle Coffee"
        assert clean_payee("AMZN Mktp US*2K91 SAN FRANCISCO CA") == "Amazon"
        assert clean_payee("TST* TAVERN ON THE GREEN REF 881923") == "Tavern on the Green"
        assert clean_payee("CHECK #1024 JOHN DOE") == "John Doe"
        assert clean_payee("CARD 4920 WEWORK SAN JOSE") == "WeWork"

    def test_classify_category_heuristics(self):
        assert classify_category("Direct Deposit Payroll Acme") == "Income / Payroll"
        assert classify_category("Pacific Gas & Electric Utility") == "Utilities"
        assert classify_category("Whole Foods Market") == "Groceries"
        assert classify_category("Starbucks Coffee") == "Dining / Food"
        assert classify_category("WeWork Office Rent") == "Rent & Mortgage"
        assert classify_category("Amazon Web Services Cloud") == "Software & Subscriptions"
        assert classify_category("Zelle Transfer to Jane") == "Transfers & Wire"
        assert classify_category("Monthly Account Maintenance Fee") == "Bank Fees"
        assert classify_category("CVS Pharmacy") == "Healthcare & Medical"
        assert classify_category("Uber Trip 124") == "Travel & Transportation"
        assert classify_category("Target Retail Store") == "Shopping & Retail"
        assert classify_category("Geico Auto Insurance") == "Insurance"
        assert classify_category("US Treasury IRS Tax Payment") == "Taxes"
        assert classify_category("Random Merchant Unknown") == "Miscellaneous"


class TestDocumentRouter:
    def test_detect_image_formats(self):
        png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        webp_bytes = b"RIFF\x00\x00\x00\x00WEBPVP8"

        assert detect_document_type(png_bytes, "test.png") == "raster_image"
        assert detect_document_type(jpeg_bytes, "test.jpg") == "raster_image"
        assert detect_document_type(webp_bytes, "test.webp") == "raster_image"
        assert detect_document_type(b"some bytes", "receipt.png", mime_type="image/png") == "raster_image"

    def test_detect_digital_vs_scanned_pdf(self):
        # Generate a real digital PDF with substantial text
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        story = [
            Paragraph("Bank of America Account Statement", styles["Title"]),
            Paragraph("Account Number: ************8842", styles["Normal"]),
            Paragraph("Starting Balance: $2,500.00 Ending Balance: $4,500.00", styles["Normal"]),
            Paragraph("Here is substantial vector text well over the 50 character per page threshold.", styles["Normal"]),
        ]
        doc.build(story)
        digital_pdf_bytes = buffer.getvalue()

        assert detect_document_type(digital_pdf_bytes, "statement.pdf") == "digital_pdf"


class TestComputerVisionPreprocessing:
    def test_image_preprocessing_pipeline(self):
        # Create a synthetic image with text
        img = Image.new("RGB", (400, 200), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)
        draw.text((20, 50), "Bank Statement 2026", fill=(0, 0, 0))
        draw.text((20, 100), "Starting Balance: $1000.00", fill=(0, 0, 0))

        prep_np = preprocess_image(img)
        assert isinstance(prep_np, np.ndarray)
        assert len(prep_np.shape) == 2  # Grayscale / binarized single channel
        assert prep_np.shape == (200, 400)


class TestDigitalPDFExtraction:
    def _create_synthetic_pdf(self) -> bytes:
        """Generates a pixel-perfect ReportLab synthetic digital PDF bank statement."""
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        story = []

        # Header & Metadata
        story.append(Paragraph("<b>Apex Global Commercial Bank</b>", styles["Title"]))
        story.append(Paragraph("Account Statement | Period: 09/01/2026 - 09/30/2026", styles["Normal"]))
        story.append(Spacer(1, 12))

        summary_data = [
            ["Account Number:", "************8842", "Starting Balance:", "$2,500.00"],
            ["Statement Period:", "09/01/2026 - 09/30/2026", "Ending Balance:", "$5,907.31"],
        ]
        summary_table = Table(summary_data, colWidths=[120, 150, 120, 150])
        story.append(summary_table)
        story.append(Spacer(1, 16))

        # Transactions Table (Two-column debits & credits format)
        table_rows = [
            ["Date", "Description", "Debits (-)", "Credits (+)", "Balance"],
            ["2026-09-01", "Direct Deposit Payroll Acme Corp", "", "$3,200.00", "$5,700.00"],
            ["2026-09-03", "Whole Foods Market Grocery", "$142.50", "", "$5,557.50"],
            ["2026-09-05", "Pacific Gas & Electric Utility", "$85.20", "", "$5,472.30"],
            ["2026-09-12", "Amazon Marketplace Retail", "$64.99", "", "$5,407.31"],
            ["2026-09-18", "Client Wire Transfer Inflow", "", "$1,500.00", "$6,907.31"],
            ["2026-09-24", "WeWork Office Rent", "$1,000.00", "", "$5,907.31"],
        ]
        tx_table = Table(table_rows, colWidths=[70, 220, 80, 80, 80])
        tx_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ]
            )
        )
        story.append(tx_table)
        doc.build(story)
        return buf.getvalue()

    def test_extract_digital_pdf_metadata_and_transactions(self):
        pdf_bytes = self._create_synthetic_pdf()
        metadata, records = extract_digital_pdf(pdf_bytes)

        assert metadata.bank_name == "Apex Global Commercial Bank"
        assert metadata.account_number == "************8842"
        assert metadata.statement_period_start == "2026-09-01"
        assert metadata.statement_period_end == "2026-09-30"
        assert metadata.starting_balance == "2500.00"
        assert metadata.ending_balance == "5907.31"

        assert len(records) == 6
        # Verify first transaction (Credit)
        assert records[0].date == "2026-09-01"
        assert records[0].type == "credit"
        assert records[0].amount == "3200.00"
        assert records[0].running_balance == "5700.00"
        assert records[0].category == "Income / Payroll"

        # Verify second transaction (Debit)
        assert records[1].date == "2026-09-03"
        assert records[1].type == "debit"
        assert records[1].amount == "142.50"
        assert records[1].running_balance == "5557.50"
        assert records[1].category == "Groceries"

    def test_multi_page_pdf_with_wrapped_descriptions(self):
        """Tests multi-page statements with line-wrapped payee descriptions."""
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()
        story = []

        # Page 1 Header
        story.append(Paragraph("<b>Chase Bank</b>", styles["Title"]))
        story.append(Paragraph("Account Number: 1234567890", styles["Normal"]))
        story.append(Paragraph("Starting Balance: $1,000.00 Ending Balance: $1,650.00", styles["Normal"]))
        story.append(Spacer(1, 10))

        page1_rows = [
            ["Date", "Description", "Debits", "Credits", "Balance"],
            ["2026-09-01", "Client Deposit Inflow", "", "$1,000.00", "$2,000.00"],
            ["2026-09-05", "SQ *BLUE BOTTLE COFFEE", "$50.00", "", "$1,950.00"],
            ["", "SAN FRANCISCO CA REF 98213", "", "", ""],  # Wrapped description row!
        ]
        t1 = Table(page1_rows, colWidths=[70, 220, 80, 80, 80])
        story.append(t1)

        # Page Break
        story.append(PageBreak())

        # Page 2 Repeated Header & Continued Table
        story.append(Paragraph("<b>Chase Bank</b>", styles["Title"]))
        story.append(Paragraph("Page 2 of 2", styles["Normal"]))
        story.append(Spacer(1, 10))

        page2_rows = [
            ["Date", "Description", "Debits", "Credits", "Balance"],  # Repeated header
            ["2026-09-15", "WeWork Coworking Space", "$300.00", "", "$1,650.00"],
        ]
        t2 = Table(page2_rows, colWidths=[70, 220, 80, 80, 80])
        story.append(t2)

        doc.build(story)
        pdf_bytes = buf.getvalue()

        metadata, records = extract_digital_pdf(pdf_bytes)
        assert metadata.bank_name == "Chase"
        assert metadata.account_number == "1234567890"
        assert len(records) == 3

        # Wrapped description check
        assert "BLUE BOTTLE" in records[1].raw_description
        assert "SAN FRANCISCO" in records[1].raw_description
        assert records[1].payee == "Blue Bottle Coffee"
        assert records[1].category == "Dining / Food"

        # Page 2 transaction
        assert records[2].payee == "WeWork"
        assert records[2].category == "Rent & Mortgage"


class TestOCRAndImageExtraction:
    def test_pypdfium2_rasterizer(self):
        # Generate simple PDF
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter)
        styles = getSampleStyleSheet()
        doc.build([Paragraph("Test Rasterization", styles["Title"])])
        pdf_bytes = buf.getvalue()

        images = render_pdf_to_images(pdf_bytes, dpi=150)
        assert len(images) == 1
        assert isinstance(images[0], Image.Image)
        assert images[0].width > 0 and images[0].height > 0

    def test_rapidocr_on_synthetic_image(self):
        # Create an image containing clear text
        img = Image.new("RGB", (600, 200), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 40), "2026-09-01 Starting Balance: $1000.00", fill=(0, 0, 0))
        draw.text((20, 90), "2026-09-05 Coffee Shop $5.50 $994.50", fill=(0, 0, 0))

        text, conf = run_ocr_on_image(img)
        assert "2026" in text or "Balance" in text or "Coffee" in text
        assert conf > 0.5


class TestEndToEndParsingAndReconciliation:
    def test_parse_statement_full_reconciliation(self):
        """
        End-to-end integration test parsing a digital PDF,
        running reconciliation, and returning a validated StatementParseResult.
        """
        # Generate the synthetic statement
        test_pdf_fixture = TestDigitalPDFExtraction()._create_synthetic_pdf()

        result = parse_statement(test_pdf_fixture, filename="apex_statement.pdf")

        assert isinstance(result, StatementParseResult)
        assert result.document_type == "digital_pdf"
        assert result.parsing_engine == "pdfplumber"

        # Metadata assertions
        assert result.metadata.bank_name == "Apex Global Commercial Bank"
        assert result.metadata.account_number == "************8842"
        assert result.metadata.starting_balance == "2500.00"
        assert result.metadata.ending_balance == "5907.31"

        # Transactions assertions
        assert len(result.transactions) == 6

        # Reconciliation assertions
        assert result.reconciliation.is_reconciled is True
        assert result.reconciliation.starting_balance == "2500.00"
        assert result.reconciliation.reported_ending_balance == "5907.31"
        assert result.reconciliation.calculated_ending_balance == "5907.31"
        assert result.reconciliation.discrepancy == "0.00"
        assert result.reconciliation.total_credits == "4700.00"  # 3200 + 1500
        assert result.reconciliation.total_debits == "1292.69"   # 142.50 + 85.20 + 64.99 + 1000.00
        assert result.reconciliation.net_cashflow == "3407.31"  # 4700.00 - 1292.69

    def test_deskew_image_angle_correction(self):
        """Tests that deskew_image processes an image without error."""
        img = np.ones((300, 500), dtype=np.uint8) * 255
        # Draw some dark text-like bars
        cv2.putText(img, "TEST BANK STATEMENT 2026", (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
        deskewed = deskew_image(img)
        assert isinstance(deskewed, np.ndarray)
        assert deskewed.shape == (300, 500)

    def test_parse_raster_image_statement(self):
        """Tests parsing a statement submitted as a PNG image."""
        img = Image.new("RGB", (700, 300), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 20), "Apex Global Commercial Bank", fill=(0, 0, 0))
        draw.text((20, 50), "Starting Balance: $1,000.00 Ending Balance: $1,950.00", fill=(0, 0, 0))
        draw.text((20, 90), "2026-09-01 Client Inflow $1000.00 $2000.00", fill=(0, 0, 0))
        draw.text((20, 130), "2026-09-05 Coffee Shop $50.00 $1950.00", fill=(0, 0, 0))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        result = parse_statement(png_bytes, filename="statement.png", mime_type="image/png")
        assert result.document_type == "raster_image"
        assert result.parsing_engine == "rapidocr"
        assert len(result.transactions) >= 1

    def test_gemini_vision_fallback_mock(self, monkeypatch):
        """Tests Gemini Multimodal Vision AI fallback when configured."""
        fake_response_data = {
            "metadata": {
                "bank_name": "Gemini AI Bank",
                "account_number": "1111222233334444",
                "statement_period_start": "2026-09-01",
                "statement_period_end": "2026-09-30",
                "starting_balance": "1000.00",
                "ending_balance": "1500.00",
                "currency": "USD"
            },
            "transactions": [
                {
                    "date": "2026-09-02",
                    "payee": "Direct Deposit",
                    "type": "credit",
                    "amount": "500.00",
                    "running_balance": "1500.00",
                    "raw_description": "Direct Deposit ACH"
                }
            ]
        }

        class FakeResponse:
            text = json.dumps(fake_response_data)

        class FakeModels:
            def generate_content(self, *args, **kwargs):
                return FakeResponse()

        class FakeClient:
            def __init__(self, *args, **kwargs):
                self.models = FakeModels()

        from google import genai
        monkeypatch.setenv("GEMINI_API_KEY", "fake_test_key")
        monkeypatch.setattr(genai, "Client", FakeClient)

        from app.services.parser.vision_ai import extract_with_gemini_vision, is_gemini_available
        assert is_gemini_available() is True

        metadata, txs = extract_with_gemini_vision(b"dummy_bytes", mime_type="application/pdf")
        assert metadata.bank_name == "Gemini AI Bank"
        assert metadata.starting_balance == "1000.00"
        assert metadata.ending_balance == "1500.00"
        assert len(txs) == 1
        assert txs[0].amount == "500.00"
        assert txs[0].type == "credit"
