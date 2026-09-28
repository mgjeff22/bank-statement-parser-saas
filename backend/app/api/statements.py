import os
import io
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.statement import StatementRecord
from app.schemas.dashboard import StatementHistoryItem
from app.services.quota import check_quota, record_usage, refund_usage

router = APIRouter()


@router.post("/upload")
async def upload_statement(
    file: UploadFile = File(...),
    filename: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ingests and parses a bank statement (PDF or image).
    Applies pre-flight quota gating, atomic decrement, pipeline parsing, and records metadata.
    """
    file_bytes = await file.read()
    target_filename = filename or file.filename or "statement.pdf"

    # Calculate page count
    page_count = 1
    if file_bytes.startswith(b"%PDF"):
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            page_count = len(reader.pages)
        except Exception:
            page_count = file_bytes.count(b"/Page\n") + file_bytes.count(b"/Page ")
            if page_count <= 0:
                page_count = 1

    # 1. Pre-flight quota check
    check_quota(current_user.tenant_id, page_count, db)

    # 2. Atomic decrement
    record_usage(current_user.tenant_id, page_count, db)

    # 3. Store uploaded file locally
    statement_id = f"stmt_{uuid.uuid4().hex[:12]}"
    safe_filename = os.path.basename(target_filename)
    file_path = os.path.join(settings.UPLOAD_DIR, f"{statement_id}_{safe_filename}")

    try:
        with open(file_path, "wb") as f:
            f.write(file_bytes)
    except Exception as e:
        refund_usage(current_user.tenant_id, page_count, db)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to write file to storage: {str(e)}",
        )

    # 4. Invoke parsing pipeline
    try:
        from app.services.parser.router import parse_statement
        parsed_result = parse_statement(file_bytes, filename=target_filename)
        status_val = "error" if parsed_result.error_message and len(parsed_result.transactions) == 0 else "completed"
    except Exception as e:
        refund_usage(current_user.tenant_id, page_count, db)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal parsing error: {str(e)}",
        )

    # 5. Record statement in database
    metadata = parsed_result.metadata
    reconciliation = parsed_result.reconciliation

    stmt_record = StatementRecord(
        id=statement_id,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        filename=target_filename,
        file_path=file_path,
        status=status_val,
        page_count=page_count,
        bank_name=metadata.bank_name if metadata else None,
        statement_period_start=metadata.statement_period_start if metadata else None,
        statement_period_end=metadata.statement_period_end if metadata else None,
        starting_balance=metadata.starting_balance if metadata else None,
        ending_balance=metadata.ending_balance if metadata else None,
        total_credits=reconciliation.total_credits if reconciliation else None,
        total_debits=reconciliation.total_debits if reconciliation else None,
        net_cashflow=reconciliation.net_cashflow if reconciliation else None,
        discrepancy=reconciliation.discrepancy if reconciliation else None,
        is_reconciled=reconciliation.is_reconciled if reconciliation else None,
        error_message=parsed_result.error_message,
        created_at=datetime.now(timezone.utc),
    )
    db.add(stmt_record)
    db.commit()
    db.refresh(stmt_record)

    return {
        "status_code": 200,
        "statement_id": statement_id,
        "id": statement_id,
        "filename": target_filename,
        "page_count": page_count,
        "status": status_val,
        "metadata": metadata.model_dump() if metadata else None,
        "reconciliation": reconciliation.model_dump() if reconciliation else None,
        "transactions": [tx.model_dump() for tx in parsed_result.transactions],
        "created_at": stmt_record.created_at.isoformat(),
    }


@router.get("/history", response_model=List[StatementHistoryItem])
def get_statement_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns statement upload history for the active tenant."""
    records = (
        db.query(StatementRecord)
        .filter(StatementRecord.tenant_id == current_user.tenant_id)
        .order_by(StatementRecord.created_at.desc())
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


@router.get("/{statement_id}")
def get_statement(
    statement_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves an individual statement record."""
    stmt = (
        db.query(StatementRecord)
        .filter(
            StatementRecord.id == statement_id,
            StatementRecord.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not stmt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement not found",
        )

    return {
        "statement_id": stmt.id,
        "filename": stmt.filename,
        "status": stmt.status,
        "page_count": stmt.page_count,
        "bank_name": stmt.bank_name,
        "statement_period_start": stmt.statement_period_start,
        "statement_period_end": stmt.statement_period_end,
        "starting_balance": stmt.starting_balance,
        "ending_balance": stmt.ending_balance,
        "total_credits": stmt.total_credits,
        "total_debits": stmt.total_debits,
        "net_cashflow": stmt.net_cashflow,
        "discrepancy": stmt.discrepancy,
        "is_reconciled": stmt.is_reconciled,
        "error_message": stmt.error_message,
        "created_at": stmt.created_at.isoformat(),
    }


@router.delete("/{statement_id}")
@router.delete("/{statement_id}/delete")
def delete_statement(
    statement_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deletes a statement record and cleans up associated file storage."""
    stmt = (
        db.query(StatementRecord)
        .filter(
            StatementRecord.id == statement_id,
            StatementRecord.tenant_id == current_user.tenant_id,
        )
        .first()
    )
    if not stmt:
        return {"success": False, "message": "Statement not found"}

    if stmt.file_path and os.path.exists(stmt.file_path):
        try:
            os.remove(stmt.file_path)
        except OSError:
            pass

    db.delete(stmt)
    db.commit()
    return {"success": True, "message": "Statement deleted successfully"}
