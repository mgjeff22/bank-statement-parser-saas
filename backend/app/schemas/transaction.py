"""
Transaction schemas adhering to PROJECT.md interface contracts.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field


TransactionType = Literal["debit", "credit"]
AnomalyType = Literal["SIGN_INVERSION", "MISSING_GAP", "OUT_OF_ORDER_DATE", "TRANSPOSITION"]


class TransactionRecord(BaseModel):
    id: str = Field(..., description="Unique transaction identifier")
    date: str = Field(..., description="ISO-8601 formatted date (YYYY-MM-DD)")
    payee: str = Field(..., description="Cleaned merchant/payee name or description")
    type: TransactionType = Field(..., description="debit (expense) or credit (deposit)")
    amount: str = Field(..., description="Exact Decimal string e.g. '124.50'")
    category: str = Field(default="Miscellaneous", description="Transaction category classification")
    running_balance: str = Field(..., description="Exact Decimal string e.g. '2125.50'")
    has_anomaly: bool = Field(default=False, description="Whether transaction is flagged with an anomaly")
    anomaly_type: Optional[AnomalyType] = Field(
        default=None,
        description="Type of anomaly: SIGN_INVERSION | MISSING_GAP | OUT_OF_ORDER_DATE | TRANSPOSITION"
    )
    raw_description: Optional[str] = Field(default=None, description="Original verbatim row text from document")
