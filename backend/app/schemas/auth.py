from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password")
    tier: Optional[str] = Field(default="free", description="Initial subscription tier (free, starter, pro)")
    full_name: Optional[str] = Field(default=None, description="User full name")
    organization_name: Optional[str] = Field(default=None, description="Optional organization name")


class UserLoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class UserResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    email: str
    tenant_id: str
    subscription_tier: str
    token: str
    access_token: str
    token_type: str = "bearer"
    role: str = "owner"
    created_at: str


class UserMeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    email: str
    tenant_id: str
    role: str
    subscription_tier: str
    is_active: bool
    created_at: str
