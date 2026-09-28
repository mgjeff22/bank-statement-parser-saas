"""
Reconciliation schemas adhering to PROJECT.md interface contracts.
"""
from typing import List
from pydantic import BaseModel, Field


class ReconciliationSummary(BaseModel):
    starting_balance: str = Field(..., description="Exact Decimal string e.g. '1250.00'")
    total_credits: str = Field(..., description="Sum of all credits as Decimal string")
    total_debits: str = Field(..., description="Sum of all debits as Decimal string")
    net_cashflow: str = Field(..., description="total_credits - total_debits as Decimal string")
    calculated_ending_balance: str = Field(..., description="starting_balance + net_cashflow as Decimal string")
    reported_ending_balance: str = Field(..., description="Reported ending balance from statement")
    discrepancy: str = Field(..., description="calculated_ending_balance - reported_ending_balance")
    is_reconciled: bool = Field(..., description="True if discrepancy == '0.00'")
    diagnostic_flags: List[str] = Field(default_factory=list, description="Diagnostic anomaly flags and recommendations")
