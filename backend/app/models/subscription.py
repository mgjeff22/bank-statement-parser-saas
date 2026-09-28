import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String(64), primary_key=True, default=lambda: f"sub_{uuid.uuid4().hex[:12]}")
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    stripe_customer_id = Column(String(100), nullable=True, index=True)
    stripe_subscription_id = Column(String(100), nullable=True, unique=True)
    tier = Column(String(32), default="free", nullable=False)  # "free", "starter", "pro"
    status = Column(String(32), default="active", nullable=False)  # "active", "canceled", "past_due"
    monthly_page_limit = Column(Integer, default=5, nullable=False)  # 5, 50, 500
    current_period_start = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="subscription")
