import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime

from app.core.database import Base


class ProcessedStripeEvent(Base):
    __tablename__ = "processed_stripe_events"

    id = Column(String(64), primary_key=True, default=lambda: f"pse_{uuid.uuid4().hex[:12]}")
    event_id = Column(String(100), unique=True, index=True, nullable=False)
    event_type = Column(String(100), nullable=False)
    processed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    payload_hash = Column(String(64), nullable=True)
    status = Column(String(20), default="processed", nullable=False)
