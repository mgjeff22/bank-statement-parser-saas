"""
OCR Engine and Image Preprocessing Pipeline.

Features:
- pypdfium2 CPU rasterization at 300 DPI (no system Poppler required)
- OpenCV computer vision preprocessing (Grayscale, CLAHE contrast, Deskewing, Otsu binarization)
- Local CPU ONNX OCR via RapidOCR (no system Tesseract required)
- Reading-order reconstruction (line clustering based on vertical coordinates)
"""
import io
import logging
import math
from typing import Any, List, Optional, Tuple, Union

import cv2
import numpy as np
import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError
from rapidocr_onnxruntime import RapidOCR

from app.schemas.statement import StatementMetadata
from app.schemas.transaction import TransactionRecord
from app.services.parser.digital_pdf import (
    extract_metadata_from_text,
    extract_transactions_from_text_fallback,
)

logger = logging.getLogger(__name__)


class CorruptedDocumentError(ValueError):
    """Raised when an uploaded document file is corrupted, truncated, or unreadable."""
    pass


# Lazy singleton for OCR engine
_ocr_engine_instance: Optional[RapidOCR] = None


def get_ocr_engine() -> RapidOCR:
    global _ocr_engine_instance
    if _ocr_engine_instance is None:
        _ocr_engine_instance = RapidOCR()
    return _ocr_engine_instance


def render_pdf_to_images(pdf_bytes: bytes, dpi: int = 300) -> List[Image.Image]:
    """
    Renders PDF pages to high-resolution PIL images using pypdfium2 (CPU-only, no Poppler needed).
    300 DPI corresponds to scale = 300 / 72 ≈ 4.1667.
    Returns an empty list on corrupted, truncated, or zero-byte input.
    """
    if not pdf_bytes or len(pdf_bytes) == 0:
        return []

    images = []
    pdf = None
    try:
        pdf = pdfium.PdfDocument(pdf_bytes)
        scale = dpi / 72.0
        for page in pdf:
            try:
                bitmap = page.render(scale=scale)
                pil_image = bitmap.to_pil()
                images.append(pil_image)
            except Exception as page_exc:
                logger.warning(f"Failed to render PDF page: {page_exc}")
                continue
    except (pdfium.PdfiumError, ValueError, Exception) as exc:
        logger.warning(f"Failed to load PDF document for rasterization: {exc}")
        return []
    finally:
        if pdf is not None and hasattr(pdf, "close"):
            try:
                pdf.close()
            except Exception:
                pass

    return images



def deskew_image(image_cv: np.ndarray) -> np.ndarray:
    """
    Calculates document skew angle using minAreaRect on text contours and deskews image.
    """
    if image_cv is None or not isinstance(image_cv, np.ndarray) or image_cv.size == 0:
        return image_cv
    if len(image_cv.shape) < 2 or image_cv.shape[0] == 0 or image_cv.shape[1] == 0:
        return image_cv

    try:
        if len(image_cv.shape) == 3:
            gray = cv2.cvtColor(image_cv, cv2.COLOR_BGR2GRAY)
        else:
            gray = image_cv

        # Invert colors so text pixels are foreground
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))

        if len(coords) < 100:
            return image_cv  # Insufficient text pixels to estimate skew reliably

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        elif angle > 45:
            angle = 90 - angle
        else:
            angle = -angle

        # Ignore micro-angles (< 0.25 deg) or extreme angles (> 20 deg)
        if abs(angle) < 0.25 or abs(angle) > 20:
            return image_cv

        (h, w) = image_cv.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            image_cv, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return rotated
    except Exception as exc:
        logger.warning(f"Deskew calculation failed: {exc}")
        return image_cv


def preprocess_image(image_input: Union[np.ndarray, Image.Image]) -> np.ndarray:
    """
    Applies computer vision enhancements:
    1. Grayscale conversion
    2. Automatic deskewing
    3. Adaptive Contrast (CLAHE)
    4. Otsu binarization
    Safely returns empty array if image_input is empty, corrupted, or invalid.
    """
    if image_input is None:
        return np.zeros((0, 0), dtype=np.uint8)

    try:
        if isinstance(image_input, Image.Image):
            if image_input.width == 0 or image_input.height == 0:
                return np.zeros((0, 0), dtype=np.uint8)
            img_np = np.array(image_input)
            if img_np.size == 0:
                return np.zeros((0, 0), dtype=np.uint8)
            if len(img_np.shape) == 3:
                if img_np.shape[2] == 4:
                    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
                else:
                    img_np = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        elif isinstance(image_input, np.ndarray):
            if image_input.size == 0:
                return np.zeros((0, 0), dtype=np.uint8)
            img_np = image_input.copy()
        else:
            return np.zeros((0, 0), dtype=np.uint8)

        if img_np.size == 0 or len(img_np.shape) < 2 or img_np.shape[0] == 0 or img_np.shape[1] == 0:
            return np.zeros((0, 0), dtype=np.uint8)

        # 1. Grayscale
        if len(img_np.shape) == 3:
            gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
        else:
            gray = img_np

        # 2. Deskew
        deskewed = deskew_image(gray)

        # 3. CLAHE Contrast Enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(deskewed)

        # 4. Otsu Binarization
        _, binarized = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

        return binarized
    except Exception as exc:
        logger.warning(f"Image preprocessing failed: {exc}")
        return np.zeros((0, 0), dtype=np.uint8)



def reconstruct_reading_order(ocr_results: List[Any]) -> Tuple[str, float]:
    """
    Reconstructs natural line reading order from RapidOCR bounding boxes.
    RapidOCR items: [box_points, text, confidence]
    """
    if not ocr_results:
        return "", 0.0

    items = []
    conf_scores = []
    for entry in ocr_results:
        if not entry or len(entry) < 3:
            continue
        box, text, score = entry[0], str(entry[1]).strip(), float(entry[2])
        if not text:
            continue
        # box: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
        # compute center y and left x
        y_center = sum(pt[1] for pt in box) / 4.0
        x_left = min(pt[0] for pt in box)
        y_height = max(pt[1] for pt in box) - min(pt[1] for pt in box)
        items.append({"text": text, "x": x_left, "y": y_center, "h": max(y_height, 10), "score": score})
        conf_scores.append(score)

    if not items:
        return "", 0.0

    # Sort primarily by y_center
    items.sort(key=lambda item: item["y"])

    # Cluster into lines
    lines: List[List[dict]] = []
    current_line: List[dict] = []
    line_y = None

    for item in items:
        if line_y is None:
            current_line = [item]
            line_y = item["y"]
        else:
            # If within half character height, consider on same line
            if abs(item["y"] - line_y) < (item["h"] * 0.6):
                current_line.append(item)
            else:
                # Sort current line horizontally left to right
                current_line.sort(key=lambda it: it["x"])
                lines.append(current_line)
                current_line = [item]
                line_y = item["y"]

    if current_line:
        current_line.sort(key=lambda it: it["x"])
        lines.append(current_line)

    reconstructed_lines = []
    for l in lines:
        line_text = " ".join(it["text"] for it in l)
        reconstructed_lines.append(line_text)

    full_text = "\n".join(reconstructed_lines)
    avg_conf = sum(conf_scores) / max(len(conf_scores), 1)
    return full_text, avg_conf


def run_ocr_on_image(image_input: Union[np.ndarray, Image.Image]) -> Tuple[str, float]:
    """
    Runs RapidOCR on image and returns reconstructed text and confidence.
    Safely handles empty or corrupted images without throwing unhandled exceptions.
    """
    if image_input is None:
        return "", 0.0

    try:
        prep = preprocess_image(image_input)
        if prep is None or prep.size == 0 or len(prep.shape) < 2 or prep.shape[0] == 0 or prep.shape[1] == 0:
            return "", 0.0

        engine = get_ocr_engine()
        results, _ = engine(prep)
        if not results:
            # Fallback to raw grayscale if binarization removed thin glyphs
            if isinstance(image_input, Image.Image):
                raw_np = np.array(image_input.convert("L"))
            else:
                raw_np = cv2.cvtColor(image_input, cv2.COLOR_BGR2GRAY) if len(image_input.shape) == 3 else image_input
            if raw_np is not None and raw_np.size > 0 and len(raw_np.shape) >= 2 and raw_np.shape[0] > 0 and raw_np.shape[1] > 0:
                results, _ = engine(raw_np)

        return reconstruct_reading_order(results)
    except Exception as exc:
        logger.warning(f"OCR execution failed on image: {exc}")
        return "", 0.0


def extract_scanned_or_image(
    file_bytes: bytes,
    is_pdf: bool = False,
) -> Tuple[StatementMetadata, List[TransactionRecord], float]:
    """
    Extracts statement data from scanned PDF or raster image using RapidOCR.
    Returns clean empty metadata and transaction list if the file is corrupted, empty, or unreadable.
    """
    if not file_bytes or len(file_bytes) == 0:
        metadata = extract_metadata_from_text("", default_page_count=0)
        return metadata, [], 0.0

    combined_text = ""
    confidences: List[float] = []

    if is_pdf:
        pil_images = render_pdf_to_images(file_bytes, dpi=300)
        page_count = len(pil_images)
        if not pil_images:
            metadata = extract_metadata_from_text("", default_page_count=0)
            return metadata, [], 0.0
        for img in pil_images:
            txt, conf = run_ocr_on_image(img)
            combined_text += txt + "\n"
            confidences.append(conf)
    else:
        page_count = 1
        try:
            pil_img = Image.open(io.BytesIO(file_bytes))
            pil_img.load()  # Force decode to detect corrupted/truncated buffers early
            txt, conf = run_ocr_on_image(pil_img)
            combined_text += txt + "\n"
            confidences.append(conf)
        except (UnidentifiedImageError, ValueError, OSError, Exception) as exc:
            logger.warning(f"Failed to open image for OCR extraction: {exc}")
            metadata = extract_metadata_from_text("", default_page_count=0)
            return metadata, [], 0.0

    avg_conf = sum(confidences) / max(len(confidences), 1)

    metadata = extract_metadata_from_text(combined_text, default_page_count=page_count)
    default_year = None
    if metadata.statement_period_start:
        try:
            default_year = int(metadata.statement_period_start.split("-")[0])
        except Exception:
            pass

    transactions = extract_transactions_from_text_fallback(
        combined_text,
        default_year=default_year,
        starting_balance=metadata.starting_balance,
    )

    # Derive balances if missing
    if metadata.starting_balance == "0.00" and transactions:
        first_tx = transactions[0]
        if first_tx.running_balance and first_tx.running_balance != "0.00":
            from decimal import Decimal
            first_amt = Decimal(first_tx.amount)
            first_run = Decimal(first_tx.running_balance)
            derived_start = first_run - first_amt if first_tx.type == "credit" else first_run + first_amt
            metadata.starting_balance = f"{derived_start:.2f}"

    if metadata.ending_balance == "0.00" and transactions:
        last_tx = transactions[-1]
        if last_tx.running_balance and last_tx.running_balance != "0.00":
            metadata.ending_balance = last_tx.running_balance

    return metadata, transactions, avg_conf

