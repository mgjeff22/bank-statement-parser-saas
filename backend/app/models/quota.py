import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from app.core.database import Base


class QuotaUsage(Base):
    __tablename__ = "quota_usages"

    id = Column(String(64), primary_key=True, default=lambda: f"qta_{uuid.uuid4().hex[:12]}")
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    year_month = Column(String(7), nullable=False, index=True)  # YYYY-MM
    pages_used = Column(Integer, default=0, nullable=False)
    monthly_limit = Column(Integer, default=5, nullable=False)
    last_reset_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "year_month", name="uq_tenant_year_month"),
    )

    # Relationships
    tenant = relationship("Tenant", back_populates="quota_usages")
