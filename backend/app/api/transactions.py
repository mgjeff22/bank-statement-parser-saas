"""
Transaction Management & Dynamic Reconciliation API Router.
Supports:
1. PUT /api/statements/{statement_id}/transactions: Batch update, insert, delete rows, re-reconciles in real time.
2. GET /api/statements/{statement_id}/transactions: Retrieves full editable transaction list and reconciliation.
3. POST /api/statements/{statement_id}/reconcile: Triggers explicit re-reconciliation on statement transactions.
4. POST /api/statements/reconcile: Direct in-memory reconciliation on raw transaction list.
"""
import os
import json
from typing import List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_optional, get_current_user
from app.models.user import User
from app.models.statement import StatementRecord
from app.schemas.transaction import TransactionRecord
from app.schemas.reconciliation import ReconciliationSummary
from app.services.reconciliation import reconcile_statement, to_decimal, format_decimal

router = APIRouter()


class BatchTransactionsPayload(BaseModel):
    transactions: List[TransactionRecord] = Field(default_factory=list, description="Updated full transaction list")
    starting_balance: Optional[str] = Field(default=None, description="Optional override for starting balance")
    ending_balance: Optional[str] = Field(default=None, description="Optional override for ending balance")


class DirectReconcileRequest(BaseModel):
    starting_balance: str = Field(..., description="Starting balance Decimal string e.g. '1000.00'")
    reported_ending_balance: str = Field(..., description="Reported ending balance Decimal string e.g. '1500.00'")
    transactions: List[TransactionRecord] = Field(default_factory=list, description="Transactions to reconcile")


def _get_statement_or_404(statement_id: str, db: Session, user: Optional[User] = None) -> StatementRecord:
    query = db.query(StatementRecord).filter(StatementRecord.id == statement_id)
    if user:
        query = query.filter(StatementRecord.tenant_id == user.tenant_id)
    stmt = query.first()
    if not stmt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Statement '{statement_id}' not found.",
        )
    return stmt


def _load_transactions(stmt: StatementRecord) -> List[TransactionRecord]:
    tx_file = os.path.join(settings.UPLOAD_DIR, f"{stmt.id}_transactions.json")
    if os.path.exists(tx_file):
        try:
            with open(tx_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [TransactionRecord(**item) for item in data]
        except Exception:
            pass

    # Fallback to extracting from file if not cached
    if stmt.file_path and os.path.exists(stmt.file_path):
        try:
            from app.services.parser.router import parse_statement
            with open(stmt.file_path, "rb") as f:
                file_bytes = f.read()
            parsed = parse_statement(file_bytes, filename=stmt.filename)
            _save_transactions(stmt.id, parsed.transactions)
            return parsed.transactions
        except Exception:
            pass

    return []


def _save_transactions(statement_id: str, txs: List[TransactionRecord]) -> None:
    tx_file = os.path.join(settings.UPLOAD_DIR, f"{statement_id}_transactions.json")
    with open(tx_file, "w", encoding="utf-8") as f:
        json.dump([tx.model_dump() for tx in txs], f, indent=2)


# ---------------------------------------------------------------------------
# Direct / In-Memory Reconciliation (Feature 28)
# ---------------------------------------------------------------------------

@router.post("/reconcile", response_model=ReconciliationSummary)
def direct_reconcile(payload: DirectReconcileRequest):
    """
    Direct in-memory mathematical reconciliation across submitted transactions.
    Computes Net Cashflow, Ending Balance, Discrepancy, and diagnostic anomaly flags.
    Adheres strictly to zero floating-point drift.
    """
    rec_summary, _ = reconcile_statement(
        starting_balance=payload.starting_balance,
        ending_balance=payload.reported_ending_balance,
        transactions=payload.transactions,
    )
    return rec_summary


# ---------------------------------------------------------------------------
# Statement Transaction Endpoints
# ---------------------------------------------------------------------------

@router.get("/{statement_id}/transactions")
def get_statement_transactions_endpoint(
    statement_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Retrieves all extracted/edited transactions for a given statement,
    alongside live reconciliation metrics.
    """
    stmt = _get_statement_or_404(statement_id, db, current_user)
    txs = _load_transactions(stmt)

    start_bal = stmt.starting_balance or "0.00"
    end_bal = stmt.ending_balance or "0.00"
    rec_summary, flagged_txs = reconcile_statement(start_bal, end_bal, txs)

    return {
        "statement_id": stmt.id,
        "filename": stmt.filename,
        "starting_balance": start_bal,
        "ending_balance": end_bal,
        "reconciliation": rec_summary.model_dump(),
        "transactions": [tx.model_dump() for tx in flagged_txs],
    }


@router.put("/{statement_id}/transactions")
def update_statement_transactions(
    statement_id: str,
    payload: Union[BatchTransactionsPayload, List[TransactionRecord]],
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Batch updates transactions for a statement (inline edits, additions, deletions, reorderings).
    Persists updated transactions, re-runs strict Decimal reconciliation,
    and updates StatementRecord in the database.
    """
    stmt = _get_statement_or_404(statement_id, db, current_user)

    if isinstance(payload, list):
        tx_list = payload
        start_bal = stmt.starting_balance or "0.00"
        end_bal = stmt.ending_balance or "0.00"
    else:
        tx_list = payload.transactions
        start_bal = payload.starting_balance or stmt.starting_balance or "0.00"
        end_bal = payload.ending_balance or stmt.ending_balance or "0.00"

    # Re-run reconciliation on the new transaction stream
    rec_summary, flagged_txs = reconcile_statement(start_bal, end_bal, tx_list)

    # Persist transactions
    _save_transactions(stmt.id, flagged_txs)

    # Update database record
    stmt.starting_balance = start_bal
    stmt.ending_balance = end_bal
    stmt.total_credits = rec_summary.total_credits
    stmt.total_debits = rec_summary.total_debits
    stmt.net_cashflow = rec_summary.net_cashflow
    stmt.discrepancy = rec_summary.discrepancy
    stmt.is_reconciled = rec_summary.is_reconciled

    db.commit()
    db.refresh(stmt)

    return {
        "success": True,
        "statement_id": stmt.id,
        "reconciliation": rec_summary.model_dump(),
        "transactions": [tx.model_dump() for tx in flagged_txs],
        "message": "Transactions updated and reconciliation recalculated successfully.",
    }


@router.post("/{statement_id}/reconcile", response_model=ReconciliationSummary)
def trigger_statement_reconciliation(
    statement_id: str,
    override_payload: Optional[BatchTransactionsPayload] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Re-runs the reconciliation engine for a statement.
    Updates DB status and returns the authoritative reconciliation summary.
    """
    stmt = _get_statement_or_404(statement_id, db, current_user)

    if override_payload and override_payload.transactions:
        txs = override_payload.transactions
        start_bal = override_payload.starting_balance or stmt.starting_balance or "0.00"
        end_bal = override_payload.ending_balance or stmt.ending_balance or "0.00"
    else:
        txs = _load_transactions(stmt)
        start_bal = stmt.starting_balance or "0.00"
        end_bal = stmt.ending_balance or "0.00"

    rec_summary, flagged_txs = reconcile_statement(start_bal, end_bal, txs)
    _save_transactions(stmt.id, flagged_txs)

    stmt.starting_balance = start_bal
    stmt.ending_balance = end_bal
    stmt.total_credits = rec_summary.total_credits
    stmt.total_debits = rec_summary.total_debits
    stmt.net_cashflow = rec_summary.net_cashflow
    stmt.discrepancy = rec_summary.discrepancy
    stmt.is_reconciled = rec_summary.is_reconciled

    db.commit()
    db.refresh(stmt)

    return rec_summary
