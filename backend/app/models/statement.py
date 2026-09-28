import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class StatementRecord(Base):
    __tablename__ = "statements"

    id = Column(String(64), primary_key=True, default=lambda: f"stmt_{uuid.uuid4().hex[:12]}")
    tenant_id = Column(String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    status = Column(String(32), default="queued", nullable=False)  # "queued", "processing", "completed", "error"
    page_count = Column(Integer, default=1, nullable=False)
    bank_name = Column(String(255), nullable=True)
    statement_period_start = Column(String(32), nullable=True)
    statement_period_end = Column(String(32), nullable=True)
    starting_balance = Column(String(32), nullable=True)
    ending_balance = Column(String(32), nullable=True)
    total_credits = Column(String(32), nullable=True)
    total_debits = Column(String(32), nullable=True)
    net_cashflow = Column(String(32), nullable=True)
    discrepancy = Column(String(32), nullable=True)
    is_reconciled = Column(Boolean, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="statements")
    user = relationship("User", back_populates="statements")
