import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.models.tenant import Tenant
from app.models.user import User
from app.models.subscription import Subscription
from app.models.quota import QuotaUsage
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    UserResponse,
    UserMeResponse,
)
from app.services.quota import TIER_LIMITS, get_current_year_month

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(req: UserRegisterRequest, db: Session = Depends(get_db)):
    """Registers a new tenant and user, provisioning default subscription and quota."""
    # Check if user already exists
    existing = db.query(User).filter(User.email == req.email.strip().lower()).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    tier = (req.tier or "free").lower()
    if tier not in TIER_LIMITS:
        tier = "free"
    limit = TIER_LIMITS[tier]

    # Create Tenant
    tenant_id = f"ten_{uuid.uuid4().hex[:12]}"
    org_name = req.organization_name or f"{req.email.split('@')[0]}'s Organization"
    tenant = Tenant(
        id=tenant_id,
        name=org_name,
        created_at=datetime.now(timezone.utc),
    )
    db.add(tenant)
    db.flush()

    # Create User
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        email=req.email.strip().lower(),
        hashed_password=get_password_hash(req.password),
        full_name=req.full_name,
        role="owner",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)

    # Create Subscription
    subscription_id = f"sub_{uuid.uuid4().hex[:12]}"
    subscription = Subscription(
        id=subscription_id,
        tenant_id=tenant_id,
        tier=tier,
        status="active",
        monthly_page_limit=limit,
        current_period_start=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(subscription)

    # Create initial QuotaUsage
    year_month = get_current_year_month()
    quota_id = f"qta_{uuid.uuid4().hex[:12]}"
    quota = QuotaUsage(
        id=quota_id,
        tenant_id=tenant_id,
        year_month=year_month,
        pages_used=0,
        monthly_limit=limit,
        last_reset_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(quota)

    db.commit()
    db.refresh(user)

    token = create_access_token(
        {
            "sub": user.id,
            "tenant_id": user.tenant_id,
            "email": user.email,
            "role": user.role,
        }
    )

    return UserResponse(
        id=user.id,
        email=user.email,
        tenant_id=user.tenant_id,
        subscription_tier=tier,
        token=token,
        access_token=token,
        token_type="bearer",
        role=user.role,
        created_at=user.created_at.isoformat(),
    )


@router.post("/login", response_model=UserResponse)
def login(req: UserLoginRequest, db: Session = Depends(get_db)):
    """Authenticates user credentials and returns a signed JWT token."""
    user = db.query(User).filter(User.email == req.email.strip().lower()).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
        )

    sub = db.query(Subscription).filter(Subscription.tenant_id == user.tenant_id).first()
    tier = sub.tier if sub else "free"

    token = create_access_token(
        {
            "sub": user.id,
            "tenant_id": user.tenant_id,
            "email": user.email,
            "role": user.role,
        }
    )

    return UserResponse(
        id=user.id,
        email=user.email,
        tenant_id=user.tenant_id,
        subscription_tier=tier,
        token=token,
        access_token=token,
        token_type="bearer",
        role=user.role,
        created_at=user.created_at.isoformat(),
    )


@router.get("/me", response_model=UserMeResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Retrieves current user identity, role, and subscription tier."""
    sub = db.query(Subscription).filter(Subscription.tenant_id == current_user.tenant_id).first()
    tier = sub.tier if sub else "free"

    return UserMeResponse(
        id=current_user.id,
        email=current_user.email,
        tenant_id=current_user.tenant_id,
        role=current_user.role,
        subscription_tier=tier,
        is_active=current_user.is_active,
        created_at=current_user.created_at.isoformat(),
    )


@router.post("/logout")
def logout():
    """Logs out the active user session."""
    return {"message": "Logged out successfully", "success": True}
