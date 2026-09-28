"""
Document Router & Ingestion Pipeline.

Features:
- MIME type and magic-byte inspection (PDF vs PNG/JPEG/WebP/TIFF)
- Digital vector PDF vs scanned raster PDF classification (< 50 chars/page threshold)
- Automated routing to digital extractor, local RapidOCR, or Gemini Vision AI fallback
- Full end-to-end reconciliation on extracted data returning StatementParseResult
"""
import io
import logging
import os
from typing import Optional, Tuple

import pypdf

from app.schemas.reconciliation import ReconciliationSummary
from app.schemas.statement import StatementMetadata, StatementParseResult
from app.services.parser.digital_pdf import extract_digital_pdf
from app.services.parser.ocr_engine import extract_scanned_or_image
from app.services.parser.vision_ai import extract_with_gemini_vision, is_gemini_available
from app.services.reconciliation import reconcile_statement

logger = logging.getLogger(__name__)


def detect_document_type(
    file_bytes: bytes,
    filename: str = "",
    mime_type: Optional[str] = None,
) -> str:
    """
    Classifies an input file into:
    - 'digital_pdf'
    - 'scanned_pdf'
    - 'raster_image'
    """
    if not isinstance(file_bytes, (bytes, bytearray)):
        file_bytes = b""

    fn = (filename or "").lower()
    mt = (mime_type or "").lower()

    # 1. Check if image by extension, mime type, or magic bytes
    image_exts = [".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp"]
    if any(fn.endswith(ext) for ext in image_exts) or mt.startswith("image/"):
        return "raster_image"

    if (
        file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        or file_bytes.startswith(b"\xff\xd8\xff")
        or (file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16])
        or file_bytes.startswith(b"BM")
    ):
        return "raster_image"

    # 2. Check if PDF
    if fn.endswith(".pdf") or mt == "application/pdf" or file_bytes.startswith(b"%PDF-"):
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            total_pages = len(reader.pages)
            if total_pages == 0:
                return "scanned_pdf"

            total_chars = 0
            for page in reader.pages:
                text = page.extract_text() or ""
                total_chars += len(text.strip())

            avg_chars = total_chars / total_pages
            if avg_chars < 50:
                return "scanned_pdf"
            return "digital_pdf"
        except Exception:
            # If PDF parsing fails on raw text, treat as scanned PDF
            return "scanned_pdf"

    # Default fallback based on bytes
    if b"%PDF-" in file_bytes[:1024]:
        return "scanned_pdf"

    return "raster_image"


def parse_statement(
    file_bytes: bytes,
    filename: str = "statement.pdf",
    mime_type: Optional[str] = None,
) -> StatementParseResult:
    """
    Universal ingestion entrypoint for arbitrary bank statement files.
    Classifies document, applies appropriate extraction pipeline,
    and runs deterministic mathematical reconciliation.
    Guarantees no unhandled 500 crashes on corrupted, empty, or malformed inputs.
    """
    if not isinstance(file_bytes, (bytes, bytearray)):
        file_bytes = b""

    # Early defense: handle 0-byte buffers gracefully
    if len(file_bytes) == 0:
        doc_type = detect_document_type(file_bytes, filename=filename, mime_type=mime_type)
        metadata = StatementMetadata(
            bank_name="Unknown Bank",
            account_number="",
            statement_period_start="2026-01-01",
            statement_period_end="2026-01-31",
            starting_balance="0.00",
            ending_balance="0.00",
            currency="USD",
            page_count=0,
        )
        reconciliation_summary = ReconciliationSummary(
            starting_balance="0.00",
            total_credits="0.00",
            total_debits="0.00",
            net_cashflow="0.00",
            calculated_ending_balance="0.00",
            reported_ending_balance="0.00",
            discrepancy="0.00",
            is_reconciled=False,
            diagnostic_flags=["Empty file: uploaded buffer contains 0 bytes."],
        )
        return StatementParseResult(
            metadata=metadata,
            transactions=[],
            reconciliation=reconciliation_summary,
            document_type=doc_type,
            parsing_engine="none",
            error_message="Empty file: uploaded buffer contains 0 bytes.",
        )

    try:
        doc_type = detect_document_type(file_bytes, filename=filename, mime_type=mime_type)
        engine_used = "pdfplumber"

        metadata: Optional[StatementMetadata] = None
        transactions = []
        is_corrupted = False
        error_detail: Optional[str] = None

        # 1. Digital Vector PDF
        if doc_type == "digital_pdf":
            try:
                metadata, transactions = extract_digital_pdf(file_bytes)
                engine_used = "pdfplumber"
            except Exception as exc:
                logger.warning(f"Digital PDF extraction failed: {exc}")
                metadata = None
                transactions = []

            # If digital extraction produced no transactions, fallback to OCR
            if not transactions:
                doc_type = "scanned_pdf"

        # 2. Scanned PDF or Raster Image
        if doc_type in ["scanned_pdf", "raster_image"]:
            is_pdf = doc_type == "scanned_pdf"

            # Check for Gemini Multimodal Vision AI if API key is present
            if is_gemini_available():
                try:
                    vision_mime = "application/pdf" if is_pdf else (mime_type or "image/png")
                    gemini_res = extract_with_gemini_vision(file_bytes, mime_type=vision_mime)
                    if gemini_res:
                        metadata, transactions = gemini_res
                        engine_used = "gemini_multimodal"
                except Exception as exc:
                    logger.warning(f"Gemini vision extraction failed: {exc}")

            # Fallback to local CPU RapidOCR engine
            if not transactions or metadata is None:
                try:
                    metadata, transactions, conf = extract_scanned_or_image(file_bytes, is_pdf=is_pdf)
                    engine_used = "rapidocr"
                    if metadata.page_count == 0:
                        is_corrupted = True
                        error_detail = "Corrupted or unreadable document format: no pages or images could be decoded."
                except Exception as exc:
                    logger.warning(f"OCR extraction failed: {exc}")
                    is_corrupted = True
                    error_detail = f"Corrupted or unreadable document format: {exc}"
                    metadata = None
                    transactions = []

        # Fallback default metadata if still None
        if metadata is None:
            metadata = StatementMetadata(
                bank_name="Unknown Bank",
                account_number="",
                statement_period_start="2026-01-01",
                statement_period_end="2026-01-31",
                starting_balance="0.00",
                ending_balance="0.00",
                currency="USD",
                page_count=0,
            )

        # 3. Mathematical Balance Reconciliation & Anomaly Diagnostics
        reconciliation_summary, reconciled_transactions = reconcile_statement(
            starting_balance=metadata.starting_balance,
            ending_balance=metadata.ending_balance,
            transactions=transactions,
        )

        # If document was corrupted/unreadable, override reconciliation summary diagnostics
        if is_corrupted or (len(file_bytes) > 0 and not transactions and metadata.starting_balance == "0.00" and metadata.ending_balance == "0.00" and metadata.page_count == 0):
            reconciliation_summary.is_reconciled = False
            msg = error_detail or "Corrupted or unreadable document format: unable to extract text or transactions."
            reconciliation_summary.diagnostic_flags = [msg]
            return StatementParseResult(
                metadata=metadata,
                transactions=[],
                reconciliation=reconciliation_summary,
                document_type=doc_type,
                parsing_engine=engine_used,
                error_message=msg,
            )

        return StatementParseResult(
            metadata=metadata,
            transactions=reconciled_transactions,
            reconciliation=reconciliation_summary,
            document_type=doc_type,
            parsing_engine=engine_used,
        )

    except Exception as exc:
        logger.exception(f"Unhandled exception in parse_statement for '{filename}': {exc}")
        meta = StatementMetadata(
            bank_name="Unknown Bank",
            account_number="",
            statement_period_start="2026-01-01",
            statement_period_end="2026-01-31",
            starting_balance="0.00",
            ending_balance="0.00",
            currency="USD",
            page_count=0,
        )
        rec = ReconciliationSummary(
            starting_balance="0.00",
            total_credits="0.00",
            total_debits="0.00",
            net_cashflow="0.00",
            calculated_ending_balance="0.00",
            reported_ending_balance="0.00",
            discrepancy="0.00",
            is_reconciled=False,
            diagnostic_flags=[f"Document ingestion error: {type(exc).__name__}: {str(exc)}"],
        )
        return StatementParseResult(
            metadata=meta,
            transactions=[],
            reconciliation=rec,
            document_type="scanned_pdf",
            parsing_engine="none",
            error_message=f"Corrupted or unreadable document format: {type(exc).__name__}: {str(exc)}",
        )

