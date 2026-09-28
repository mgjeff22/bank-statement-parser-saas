import os
from pathlib import Path
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from app.core.config import settings

# Ensure storage directories exist if using SQLite file
if settings.DATABASE_URL.startswith("sqlite:///"):
    sqlite_file = settings.DATABASE_URL.replace("sqlite:///", "")
    if sqlite_file and sqlite_file != ":memory:":
        parent_dir = Path(sqlite_file).parent
        parent_dir.mkdir(parents=True, exist_ok=True)

# Ensure upload directory exists
upload_path = Path(settings.UPLOAD_DIR)
upload_path.mkdir(parents=True, exist_ok=True)

db_url = settings.DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

connect_args = {"check_same_thread": False} if "sqlite" in db_url else {}
pool_kwargs = {}
if "postgresql" in db_url:
    pool_kwargs = {"pool_size": 10, "max_overflow": 20, "pool_pre_ping": True}

engine = create_engine(
    db_url,
    connect_args=connect_args,
    **pool_kwargs,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """Dependency for providing database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine=None) -> None:
    """Creates all database tables defined in models."""
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.subscription import Subscription
    from app.models.quota import QuotaUsage
    from app.models.statement import StatementRecord
    from app.models.billing import ProcessedStripeEvent

    eng = target_engine or engine
    Base.metadata.create_all(bind=eng)
