import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "AI Bank Statement Parser"
    API_V1_STR: str = "/api"
    SECRET_KEY: str = "bank-statement-parser-jwt-secret-key-32-chars-minimum-secure"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database
    DATABASE_URL: str = "sqlite:///storage/data.db"

    # File Storage
    UPLOAD_DIR: str = "storage/uploads"

    # Billing Mode
    BILLING_MODE: str = "mock"
    STRIPE_SECRET_KEY: Optional[str] = "mock_secret"
    STRIPE_PUBLISHABLE_KEY: Optional[str] = "mock_pub"
    STRIPE_WEBHOOK_SECRET: Optional[str] = "mock_whsec"

    # Tier page limits
    FREE_PAGE_LIMIT: int = 5
    STARTER_PAGE_LIMIT: int = 50
    PRO_PAGE_LIMIT: int = 500


settings = Settings()
