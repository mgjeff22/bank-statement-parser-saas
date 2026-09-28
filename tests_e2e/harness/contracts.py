"""
Opaque-box Interface Contracts and Pydantic v2 Models for AI Bank Statement Parser E2E Tests.
Matches PROJECT.md interface contracts and domain specifications.
"""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict

CENT = Decimal("0.01")


def to_decimal(val: Any) -> Decimal:
    """Safely converts string, int, float, or Decimal to quantized 2-decimal Decimal."""
    if isinstance(val, Decimal):
        return val.quantize(CENT, rounding=ROUND_HALF_UP)
    if isinstance(val, (int, str)):
        clean_str = str(val).replace("$", "").replace(",", "").strip()
        if not clean_str:
            return Decimal("0.00")
        return Decimal(clean_str).quantize(CENT, rounding=ROUND_HALF_UP)
    if isinstance(val, float):
        # Convert via string representation to avoid float representation noise
        return Decimal(f"{val:.2f}").quantize(CENT, rounding=ROUND_HALF_UP)
    raise ValueError(f"Cannot convert {val!r} of type {type(val)} to Decimal")


class TransactionType(str, Enum):
    DEBIT = "debit"
    CREDIT = "credit"


class TransactionCategory(str, Enum):
    INCOME = "Income / Payroll"
    UTILITIES = "Utilities"
    GROCERIES = "Groceries"
    DINING = "Dining & Food"
    RENT_MORTGAGE = "Rent & Mortgage"
    SOFTWARE_SAAS = "Software & Subscriptions"
    TRANSFERS = "Transfers & Wire"
    BANK_FEES = "Bank Fees"
    HEALTHCARE = "Healthcare & Medical"
    TRAVEL = "Travel & Transportation"
    ENTERTAINMENT = "Entertainment"
    SHOPPING = "Shopping & Retail"
    INSURANCE = "Insurance"
    TAXES = "Taxes"
    MISCELLANEOUS = "Miscellaneous"


class AnomalyType(str, Enum):
    NONE = "NONE"
    SIGN_INVERSION = "SIGN_INVERSION"
    MISSING_GAP = "MISSING_GAP"
    OUT_OF_ORDER_DATE = "OUT_OF_ORDER_DATE"
    TRANSPOSITION = "TRANSPOSITION"
    RUNNING_BALANCE_MISMATCH = "RUNNING_BALANCE_MISMATCH"


class SubscriptionTier(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


class StatementStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"


class StatementMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bank_name: str = Field(default="Unknown Bank", description="Name of financial institution")
    account_number: str = Field(..., description="Masked or full account number")
    statement_period_start: str = Field(..., description="ISO-8601 YYYY-MM-DD")
    statement_period_end: str = Field(..., description="ISO-8601 YYYY-MM-DD")
    starting_balance: str = Field(..., description="Exact Decimal string e.g. 1250.00")
    ending_balance: str = Field(..., description="Exact Decimal string e.g. 3450.75")
    currency: str = Field(default="USD", description="ISO-4217 e.g. USD")
    page_count: int = Field(default=1, ge=1)

    @field_validator("starting_balance", "ending_balance", mode="before")
    @classmethod
    def validate_decimal_string(cls, v: Any) -> str:
        return str(to_decimal(v))


class TransactionRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(..., description="Unique deterministic or UUID transaction identifier")
    date: str = Field(..., description="ISO-8601 YYYY-MM-DD")
    payee: str = Field(..., description="Cleaned merchant/payee name")
    type: TransactionType = Field(..., description="debit or credit")
    amount: str = Field(..., description="Exact positive Decimal string e.g. 124.50")
    category: str = Field(default="Miscellaneous")
    running_balance: str = Field(..., description="Exact Decimal string e.g. 2125.50")
    has_anomaly: bool = Field(default=False)
    anomaly_type: Optional[str] = Field(default=None)

    @field_validator("amount", "running_balance", mode="before")
    @classmethod
    def validate_amount_string(cls, v: Any) -> str:
        return str(to_decimal(v))


class ReconciliationSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    starting_balance: str = Field(..., description="Starting balance string")
    total_credits: str = Field(..., description="Sum of credits")
    total_debits: str = Field(..., description="Sum of debits")
    net_cashflow: str = Field(..., description="credits - debits")
    calculated_ending_balance: str = Field(..., description="starting + credits - debits")
    reported_ending_balance: str = Field(..., description="ending balance reported on statement")
    discrepancy: str = Field(..., description="calculated - reported")
    is_reconciled: bool = Field(..., description="True if discrepancy == 0.00")
    diagnostic_flags: List[str] = Field(default_factory=list)

    @field_validator(
        "starting_balance",
        "total_credits",
        "total_debits",
        "net_cashflow",
        "calculated_ending_balance",
        "reported_ending_balance",
        "discrepancy",
        mode="before",
    )
    @classmethod
    def validate_summary_decimals(cls, v: Any) -> str:
        return str(to_decimal(v))


class ExportPayload(BaseModel):
    metadata: StatementMetadata
    reconciliation: ReconciliationSummary
    transactions: List[TransactionRecord]


class QuotaCheckResult(BaseModel):
    allowed: bool
    tier: str
    pages_used: int
    monthly_limit: int
    remaining_pages: int
    error_code: Optional[str] = None


class UserProfile(BaseModel):
    user_id: str
    email: str
    tenant_id: str
    subscription_tier: SubscriptionTier = SubscriptionTier.FREE
    pages_used_this_period: int = 0
    monthly_page_limit: int = 5
