from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.statement import StatementRecord
from app.models.subscription import Subscription
from app.schemas.dashboard import DashboardStatsResponse, StatementHistoryItem
from app.schemas.quota import QuotaStatusResponse
from app.services.quota import get_or_create_quota

router = APIRouter()


@router.get("/stats", response_model=DashboardStatsResponse)
def get_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns monthly page consumption stats against subscription quota, with upgrade warnings."""
    quota = get_or_create_quota(current_user.tenant_id, db)
    sub = db.query(Subscription).filter(Subscription.tenant_id == current_user.tenant_id).first()
    tier = sub.tier if sub else "free"

    statement_count = (
        db.query(StatementRecord)
        .filter(StatementRecord.tenant_id == current_user.tenant_id)
        .count()
    )

    remaining = max(0, quota.monthly_limit - quota.pages_used)
    percentage = round((quota.pages_used / quota.monthly_limit) * 100, 1) if quota.monthly_limit > 0 else 0.0
    warning = percentage >= 80.0

    return DashboardStatsResponse(
        pages_used=quota.pages_used,
        monthly_limit=quota.monthly_limit,
        remaining_pages=remaining,
        percentage_used=percentage,
        tier=tier,
        statement_count=statement_count,
        warning=warning,
    )


@router.get("/quota", response_model=QuotaStatusResponse)
def get_quota(
    tenant_id: Optional[str] = Query(None),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Retrieves current quota status for tenant or authenticated user."""
    resolved_tenant_id = tenant_id or (current_user.tenant_id if current_user else None)
    if not resolved_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication or tenant_id required",
        )

    quota = get_or_create_quota(resolved_tenant_id, db)
    sub = db.query(Subscription).filter(Subscription.tenant_id == resolved_tenant_id).first()
    tier = sub.tier if sub else "free"
    remaining = max(0, quota.monthly_limit - quota.pages_used)
    allowed = remaining > 0

    return QuotaStatusResponse(
        allowed=allowed,
        tier=tier,
        pages_used=quota.pages_used,
        monthly_limit=quota.monthly_limit,
        remaining_pages=remaining,
        error_code=None if allowed else "QUOTA_EXCEEDED",
    )


@router.get("/history", response_model=List[StatementHistoryItem])
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Returns paginated statement upload history for the authenticated tenant."""
    records = (
        db.query(StatementRecord)
        .filter(StatementRecord.tenant_id == current_user.tenant_id)
        .order_by(StatementRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        StatementHistoryItem(
            statement_id=r.id,
            id=r.id,
            filename=r.filename,
            file_path=r.file_path,
            status=r.status,
            page_count=r.page_count,
            bank_name=r.bank_name,
            statement_period_start=r.statement_period_start,
            statement_period_end=r.statement_period_end,
            starting_balance=r.starting_balance,
            ending_balance=r.ending_balance,
            total_credits=r.total_credits,
            total_debits=r.total_debits,
            net_cashflow=r.net_cashflow,
            discrepancy=r.discrepancy,
            is_reconciled=r.is_reconciled,
            error_message=r.error_message,
            created_at=r.created_at.isoformat(),
        )
        for r in records
    ]
