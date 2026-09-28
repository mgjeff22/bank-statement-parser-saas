import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.quota import QuotaUsage
from app.models.subscription import Subscription

TIER_LIMITS = {
    "free": settings.FREE_PAGE_LIMIT,
    "starter": settings.STARTER_PAGE_LIMIT,
    "pro": settings.PRO_PAGE_LIMIT,
}


def get_current_year_month() -> str:
    """Returns the current calendar year and month in YYYY-MM format."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def get_or_create_quota(tenant_id: str, db: Session) -> QuotaUsage:
    """
    Fetches the quota record for the tenant for the current billing cycle.
    If none exists, initializes one using the tenant's active subscription tier limit.
    """
    year_month = get_current_year_month()
    quota = (
        db.query(QuotaUsage)
        .filter(
            QuotaUsage.tenant_id == tenant_id,
            QuotaUsage.year_month == year_month,
        )
        .first()
    )

    if not quota:
        sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
        limit = sub.monthly_page_limit if sub else settings.FREE_PAGE_LIMIT
        quota = QuotaUsage(
            id=f"qta_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            year_month=year_month,
            pages_used=0,
            monthly_limit=limit,
            last_reset_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(quota)
        db.commit()
        db.refresh(quota)

    return quota


def check_quota(tenant_id: str, page_count: int, db: Session) -> QuotaUsage:
    """
    Verifies pages_used + page_count <= monthly_limit.
    If exceeded, raises HTTP 402 with structured error details.
    """
    quota = get_or_create_quota(tenant_id, db)
    sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
    tier = sub.tier if sub else "free"
    remaining = max(0, quota.monthly_limit - quota.pages_used)

    if quota.pages_used + page_count > quota.monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "QUOTA_EXCEEDED",
                "detail": "Monthly page limit exceeded",
                "message": f"Upload requires {page_count} pages, but remaining quota is {remaining}.",
                "tier": tier,
                "pages_used": quota.pages_used,
                "monthly_limit": quota.monthly_limit,
                "remaining_pages": remaining,
                "pages_requested": page_count,
            },
        )

    return quota


def record_usage(tenant_id: str, page_count: int, db: Session) -> QuotaUsage:
    """
    Atomically increments pages_used by page_count within an atomic SQL condition.
    Raises HTTP 402 if concurrent requests exceed monthly_limit.
    """
    year_month = get_current_year_month()
    quota = get_or_create_quota(tenant_id, db)

    now = datetime.now(timezone.utc).isoformat()
    result = db.execute(
        text(
            """
            UPDATE quota_usages
            SET pages_used = pages_used + :page_count,
                updated_at = :updated_at
            WHERE tenant_id = :tenant_id
              AND year_month = :year_month
              AND (pages_used + :page_count) <= monthly_limit
            """
        ),
        {
            "page_count": page_count,
            "updated_at": now,
            "tenant_id": tenant_id,
            "year_month": year_month,
        },
    )
    db.commit()

    if result.rowcount == 0:
        db.refresh(quota)
        sub = db.query(Subscription).filter(Subscription.tenant_id == tenant_id).first()
        tier = sub.tier if sub else "free"
        remaining = max(0, quota.monthly_limit - quota.pages_used)
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "QUOTA_EXCEEDED",
                "detail": "Monthly page limit exceeded",
                "message": f"Upload requires {page_count} pages, but remaining quota is {remaining}.",
                "tier": tier,
                "pages_used": quota.pages_used,
                "monthly_limit": quota.monthly_limit,
                "remaining_pages": remaining,
                "pages_requested": page_count,
            },
        )

    db.refresh(quota)
    return quota


def refund_usage(tenant_id: str, page_count: int, db: Session) -> QuotaUsage:
    """
    Rolls back / refunds page usage in the event of pipeline processing errors.
    """
    year_month = get_current_year_month()
    quota = get_or_create_quota(tenant_id, db)

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        text(
            """
            UPDATE quota_usages
            SET pages_used = MAX(0, pages_used - :page_count),
                updated_at = :updated_at
            WHERE tenant_id = :tenant_id
              AND year_month = :year_month
            """
        ),
        {
            "page_count": page_count,
            "updated_at": now,
            "tenant_id": tenant_id,
            "year_month": year_month,
        },
    )
    db.commit()
    db.refresh(quota)
    return quota
