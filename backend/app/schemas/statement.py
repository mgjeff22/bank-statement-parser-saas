"""
Statement metadata and result schemas adhering to PROJECT.md interface contracts.
"""
from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.transaction import TransactionRecord
from app.schemas.reconciliation import ReconciliationSummary


class StatementMetadata(BaseModel):
    bank_name: str = Field(default="Unknown Bank", description="Financial institution name")
    account_number: str = Field(default="", description="Account or masked account number")
    statement_period_start: str = Field(..., description="ISO-8601 formatted start date (YYYY-MM-DD)")
    statement_period_end: str = Field(..., description="ISO-8601 formatted end date (YYYY-MM-DD)")
    starting_balance: str = Field(..., description="Exact Decimal string e.g. '1250.00'")
    ending_balance: str = Field(..., description="Exact Decimal string e.g. '3450.75'")
    currency: str = Field(default="USD", description="ISO-4217 currency code e.g. 'USD'")
    account_holder_name: Optional[str] = Field(default=None, description="Extracted account holder name")
    page_count: int = Field(default=1, description="Number of pages in document")


class StatementParseResult(BaseModel):
    metadata: StatementMetadata = Field(..., description="Statement header and balance metadata")
    transactions: List[TransactionRecord] = Field(default_factory=list, description="Extracted transaction stream")
    reconciliation: ReconciliationSummary = Field(..., description="Mathematical reconciliation result")
    document_type: Optional[str] = Field(default=None, description="digital_pdf | scanned_pdf | raster_image")
    parsing_engine: Optional[str] = Field(default=None, description="pdfplumber | rapidocr | gemini_multimodal")
    error_message: Optional[str] = Field(default=None, description="Error or diagnostic message if parsing failed or was aborted")

