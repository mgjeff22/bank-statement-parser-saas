from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class QuotaCheckRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pages_count: int = Field(default=1, ge=1, description="Number of pages requested to parse")


class QuotaStatusResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    allowed: bool
    tier: str
    pages_used: int
    monthly_limit: int
    remaining_pages: int
    error_code: Optional[str] = None
