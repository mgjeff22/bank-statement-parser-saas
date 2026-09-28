import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(64), primary_key=True, default=lambda: f"ten_{uuid.uuid4().hex[:12]}")
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    subscription = relationship("Subscription", back_populates="tenant", uselist=False, cascade="all, delete-orphan")
    quota_usages = relationship("QuotaUsage", back_populates="tenant", cascade="all, delete-orphan")
    statements = relationship("StatementRecord", back_populates="tenant", cascade="all, delete-orphan")
