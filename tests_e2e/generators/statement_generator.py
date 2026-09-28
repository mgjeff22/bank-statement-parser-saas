"""
Programmatic Synthetic Bank Statement Generator using ReportLab and Pillow.
Generates:
1. Pure vector digital PDFs (ReportLab)
2. Scanned / flattened image-based PDFs (Pillow)
3. Raster image statements (PNG, JPEG, WebP) with skew/noise options
4. Statements with deliberate anomalies (Sign Inversion, Missing Rows, Out-of-Order Dates, Overdrafts)
5. Paired ground-truth JSON files for exact verification.
"""
import os
import json
import math
import random
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional, Tuple

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from PIL import Image, ImageDraw, ImageFont

from tests_e2e.harness.contracts import (
    StatementMetadata,
    TransactionRecord,
    ReconciliationSummary,
    TransactionType,
    to_decimal,
    CENT,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle


class StatementDataSpec:
    """Specification of ground truth data for a synthetic statement."""

    def __init__(
        self,
        bank_name: str,
        account_number: str,
        period_start: str,
        period_end: str,
        starting_balance: Decimal,
        raw_transactions: List[Dict[str, Any]],
        currency: str = "USD",
        layout_style: str = "standard_table",  # standard_table | two_column | signed_single
        inject_anomaly: Optional[str] = None,  # sign_inversion | missing_row | out_of_order | balance_mismatch
        anomaly_row_idx: int = 1,
    ):
        self.bank_name = bank_name
        self.account_number = account_number
        self.period_start = period_start
        self.period_end = period_end
        self.starting_balance = to_decimal(starting_balance)
        self.currency = currency
        self.layout_style = layout_style
        self.inject_anomaly = inject_anomaly
        self.anomaly_row_idx = anomaly_row_idx

        # Compute ground truth
        self.transactions: List[TransactionRecord] = []
        self._build_transactions(raw_transactions)

    def _build_transactions(self, raw_txs: List[Dict[str, Any]]):
        current_bal = self.starting_balance

        tx_list = []
        for idx, tx in enumerate(raw_txs):
            amt = to_decimal(tx["amount"])
            tx_type = TransactionType(tx["type"])
            if tx_type == TransactionType.CREDIT:
                current_bal += amt
            else:
                current_bal -= amt

            record = TransactionRecord(
                id=f"tx_{idx + 1:03d}",
                date=tx["date"],
                payee=tx["payee"],
                type=tx_type,
                amount=str(amt),
                category=tx.get("category", "Miscellaneous"),
                running_balance=str(current_bal),
                has_anomaly=False,
                anomaly_type=None,
            )
            tx_list.append(record)

        # Apply anomaly injection if requested
        if self.inject_anomaly == "sign_inversion" and len(tx_list) > self.anomaly_row_idx:
            target = tx_list[self.anomaly_row_idx]
            old_type = target.type
            new_type = TransactionType.CREDIT if old_type == TransactionType.DEBIT else TransactionType.DEBIT
            target.type = new_type
            target.has_anomaly = True
            target.anomaly_type = "SIGN_INVERSION"

        elif self.inject_anomaly == "out_of_order" and len(tx_list) > self.anomaly_row_idx + 1:
            # Swap dates between anomaly_row_idx and the next row to violate chronological order
            r1 = tx_list[self.anomaly_row_idx]
            r2 = tx_list[self.anomaly_row_idx + 1]
            temp_date = r1.date
            r1.date = r2.date
            r2.date = temp_date
            r1.has_anomaly = True
            r1.anomaly_type = "OUT_OF_ORDER_DATE"

        elif self.inject_anomaly == "missing_row" and len(tx_list) > self.anomaly_row_idx:
            # The statement will print without this row, but the reported ending balance will still be true ending balance
            omitted = tx_list.pop(self.anomaly_row_idx)
            # Recompute running balances for remaining rows
            cbal = self.starting_balance
            for t in tx_list:
                amt = to_decimal(t.amount)
                if t.type == TransactionType.CREDIT:
                    cbal += amt
                else:
                    cbal -= amt
                t.running_balance = str(cbal)

        self.transactions = tx_list
        # Ending balance calculation
        self.ending_balance = current_bal


class SyntheticStatementGenerator:
    """Generates synthetic bank statements in PDF and raster image formats."""

    @classmethod
    def generate(
        cls,
        spec: StatementDataSpec,
        output_statement_path: str,
        output_gt_json_path: str,
        format_type: str = "digital_pdf",  # digital_pdf | scanned_pdf | png | jpeg | webp
        skew_angle: float = 0.0,
        add_noise: bool = False,
    ) -> Dict[str, Any]:
        os.makedirs(os.path.dirname(os.path.abspath(output_statement_path)), exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(output_gt_json_path)), exist_ok=True)

        fmt = format_type.lower()
        if fmt == "digital_pdf":
            cls._generate_vector_pdf(spec, output_statement_path)
        elif fmt == "scanned_pdf":
            cls._generate_scanned_pdf(spec, output_statement_path, skew_angle=skew_angle, add_noise=add_noise)
        elif fmt in ["png", "jpeg", "jpg", "webp"]:
            cls._generate_raster_image(spec, output_statement_path, image_format=fmt, skew_angle=skew_angle, add_noise=add_noise)
        else:
            raise ValueError(f"Unsupported format type: {format_type}")

        # Compute reconciliation for ground truth
        reconciliation = ReferenceReconciliationOracle.compute_reconciliation(
            starting_balance=spec.starting_balance,
            reported_ending_balance=spec.ending_balance,
            transactions=spec.transactions,
        )

        # Build Ground Truth JSON
        gt_data = {
            "metadata": {
                "bank_name": spec.bank_name,
                "account_number": spec.account_number,
                "statement_period_start": spec.period_start,
                "statement_period_end": spec.period_end,
                "starting_balance": str(spec.starting_balance),
                "ending_balance": str(spec.ending_balance),
                "currency": spec.currency,
                "page_count": 1 if len(spec.transactions) <= 12 else math.ceil(len(spec.transactions) / 12),
            },
            "transactions": [tx.model_dump() for tx in spec.transactions],
            "reconciliation": reconciliation.model_dump(),
            "generator_spec": {
                "format_type": format_type,
                "layout_style": spec.layout_style,
                "injected_anomaly": spec.inject_anomaly,
                "skew_angle": skew_angle,
                "has_noise": add_noise,
            },
        }

        with open(output_gt_json_path, "w", encoding="utf-8") as f:
            json.dump(gt_data, f, indent=2)

        return gt_data

    @classmethod
    def _generate_vector_pdf(cls, spec: StatementDataSpec, pdf_path: str):
        """Generates a clean vector PDF using ReportLab."""
        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )
        story = []
        styles = getSampleStyleSheet()

        # Bank Header
        title_style = ParagraphStyle(
            "BankTitle",
            parent=styles["Title"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            alignment=0,
        )
        subtitle_style = ParagraphStyle(
            "BankSubtitle",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#475569"),
        )

        story.append(Paragraph(f"<b>{spec.bank_name}</b>", title_style))
        story.append(Paragraph(f"Account Statement | Billing Cycle: {spec.period_start} to {spec.period_end}", subtitle_style))
        story.append(Spacer(1, 14))

        # Metadata Summary Card
        summary_data = [
            ["Account Number:", spec.account_number, "Starting Balance:", f"${spec.starting_balance:,.2f}"],
            ["Currency:", spec.currency, "Ending Balance:", f"${spec.ending_balance:,.2f}"],
        ]
        summary_table = Table(summary_data, colWidths=[110, 160, 110, 160])
        summary_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1e293b")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(summary_table)
        story.append(Spacer(1, 16))

        # Transaction Table Construction based on layout_style
        if spec.layout_style == "two_column":
            headers = ["Date", "Description", "Withdrawals (-)", "Deposits (+)", "Balance"]
            col_widths = [75, 215, 80, 80, 90]
            table_rows = [headers]
            for tx in spec.transactions:
                amt = to_decimal(tx.amount)
                debit_str = f"${amt:,.2f}" if tx.type == TransactionType.DEBIT else ""
                credit_str = f"${amt:,.2f}" if tx.type == TransactionType.CREDIT else ""
                bal_str = f"${to_decimal(tx.running_balance):,.2f}"
                table_rows.append([tx.date, tx.payee, debit_str, credit_str, bal_str])

        elif spec.layout_style == "signed_single":
            headers = ["Date", "Description", "Amount", "Balance"]
            col_widths = [85, 275, 90, 90]
            table_rows = [headers]
            for tx in spec.transactions:
                amt = to_decimal(tx.amount)
                sign = "+" if tx.type == TransactionType.CREDIT else "-"
                amt_str = f"{sign}${amt:,.2f}"
                bal_str = f"${to_decimal(tx.running_balance):,.2f}"
                table_rows.append([tx.date, tx.payee, amt_str, bal_str])

        else:  # standard_table
            headers = ["Date", "Description", "Type", "Amount", "Balance"]
            col_widths = [75, 235, 60, 85, 85]
            table_rows = [headers]
            for tx in spec.transactions:
                amt = to_decimal(tx.amount)
                bal_str = f"${to_decimal(tx.running_balance):,.2f}"
                table_rows.append([tx.date, tx.payee, tx.type.value.upper(), f"${amt:,.2f}", bal_str])

        tx_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        tx_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
                ("TOPPADDING", (0, 0), (-1, 0), 5),
                ("FONTSIZE", (0, 1), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ])
        )
        story.append(tx_table)

        doc.build(story)

    @classmethod
    def _render_statement_image(
        cls,
        spec: StatementDataSpec,
        width: int = 1700,
        height: int = 2200,
        skew_angle: float = 0.0,
        add_noise: bool = False,
    ) -> Image.Image:
        """Renders high-resolution raster image of the statement using Pillow."""
        img = Image.new("RGB", (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Header background banner
        draw.rectangle([(60, 60), (width - 60, 140)], fill=(30, 41, 59))
        draw.text((80, 80), spec.bank_name.upper(), fill=(255, 255, 255))
        draw.text((80, 110), f"OFFICIAL ACCOUNT STATEMENT | PERIOD: {spec.period_start} TO {spec.period_end}", fill=(203, 213, 225))

        # Metadata Card
        draw.rectangle([(60, 160), (width - 60, 260)], outline=(203, 213, 225), width=2, fill=(248, 250, 252))
        draw.text((80, 180), f"Account Number: {spec.account_number}", fill=(15, 23, 42))
        draw.text((80, 220), f"Currency: {spec.currency}", fill=(15, 23, 42))
        draw.text((width // 2, 180), f"Starting Balance: ${spec.starting_balance:,.2f}", fill=(15, 23, 42))
        draw.text((width // 2, 220), f"Ending Balance:   ${spec.ending_balance:,.2f}", fill=(15, 23, 42))

        # Table Header
        y = 300
        draw.rectangle([(60, y), (width - 60, y + 45)], fill=(51, 65, 85))
        draw.text((80, y + 12), "DATE", fill=(255, 255, 255))
        draw.text((280, y + 12), "DESCRIPTION / PAYEE", fill=(255, 255, 255))
        draw.text((880, y + 12), "TYPE", fill=(255, 255, 255))
        draw.text((1100, y + 12), "AMOUNT", fill=(255, 255, 255))
        draw.text((1380, y + 12), "RUNNING BALANCE", fill=(255, 255, 255))

        y += 45
        for idx, tx in enumerate(spec.transactions):
            bg = (248, 250, 252) if idx % 2 == 1 else (255, 255, 255)
            draw.rectangle([(60, y), (width - 60, y + 45)], fill=bg, outline=(226, 232, 240))
            draw.text((80, y + 12), tx.date, fill=(15, 23, 42))
            draw.text((280, y + 12), tx.payee[:45], fill=(15, 23, 42))
            draw.text((880, y + 12), tx.type.value.upper(), fill=(15, 23, 42))
            draw.text((1100, y + 12), f"${to_decimal(tx.amount):,.2f}", fill=(15, 23, 42))
            draw.text((1380, y + 12), f"${to_decimal(tx.running_balance):,.2f}", fill=(15, 23, 42))
            y += 45
            if y > height - 100:
                break

        # Apply skew rotation if requested
        if abs(skew_angle) > 0.01:
            img = img.rotate(skew_angle, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))

        # Add speckle noise if requested
        if add_noise:
            pixels = img.load()
            for _ in range(5000):
                rx = random.randint(0, width - 1)
                ry = random.randint(0, height - 1)
                gray = random.randint(180, 240)
                pixels[rx, ry] = (gray, gray, gray)

        return img

    @classmethod
    def _generate_raster_image(
        cls,
        spec: StatementDataSpec,
        image_path: str,
        image_format: str = "png",
        skew_angle: float = 0.0,
        add_noise: bool = False,
    ):
        img = cls._render_statement_image(spec, skew_angle=skew_angle, add_noise=add_noise)
        fmt = image_format.upper()
        if fmt == "JPG":
            fmt = "JPEG"
        img.save(image_path, format=fmt)

    @classmethod
    def _generate_scanned_pdf(
        cls,
        spec: StatementDataSpec,
        pdf_path: str,
        skew_angle: float = 0.0,
        add_noise: bool = False,
    ):
        """Generates a scanned/flattened image PDF where pages are pure bitmaps."""
        img = cls._render_statement_image(spec, skew_angle=skew_angle, add_noise=add_noise)
        # Convert RGB image directly into a single/multi-page PDF
        img.save(pdf_path, "PDF", resolution=300.0)
