from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class DashboardStatsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pages_used: int
    monthly_limit: int
    remaining_pages: int
    percentage_used: float
    tier: str
    statement_count: int
    warning: bool = False


class StatementHistoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    statement_id: str
    id: str
    filename: str
    file_path: Optional[str] = None
    status: str
    page_count: int
    bank_name: Optional[str] = None
    statement_period_start: Optional[str] = None
    statement_period_end: Optional[str] = None
    starting_balance: Optional[str] = None
    ending_balance: Optional[str] = None
    total_credits: Optional[str] = None
    total_debits: Optional[str] = None
    net_cashflow: Optional[str] = None
    discrepancy: Optional[str] = None
    is_reconciled: Optional[bool] = None
    error_message: Optional[str] = None
    created_at: str
