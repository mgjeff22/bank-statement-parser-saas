"""
Data Export API Endpoints.
Provides:
1. Direct payload export: POST /api/export/{format_type} (csv, xlsx, json)
2. Statement-based export: GET /api/export/{statement_id}/{format_type} and POST /api/export/{statement_id}/{format_type}
3. Programmatic round-trip verification: POST /api/export/verify
"""
import os
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user_optional, get_current_user
from app.models.user import User
from app.models.statement import StatementRecord
from app.schemas.statement import StatementMetadata
from app.schemas.transaction import TransactionRecord
from app.schemas.reconciliation import ReconciliationSummary
from app.services.reconciliation import reconcile_statement
from app.services.exporter import (
    ExportPayload,
    export_to_csv,
    export_to_xlsx,
    export_to_json,
    verify_round_trip,
)

router = APIRouter()


def _get_statement_transactions(stmt: StatementRecord) -> List[TransactionRecord]:
    """Helper to retrieve or reconstruct transaction records for a statement."""
    tx_file = os.path.join(settings.UPLOAD_DIR, f"{stmt.id}_transactions.json")
    if os.path.exists(tx_file):
        try:
            with open(tx_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [TransactionRecord(**item) for item in data]
        except Exception:
            pass

    # If transactions file doesn't exist, attempt to parse source file if available
    if stmt.file_path and os.path.exists(stmt.file_path):
        try:
            from app.services.parser.router import parse_statement
            with open(stmt.file_path, "rb") as f:
                file_bytes = f.read()
            parsed = parse_statement(file_bytes, filename=stmt.filename)
            # Cache transactions for fast subsequent reads
            try:
                with open(tx_file, "w", encoding="utf-8") as f:
                    json.dump([tx.model_dump() for tx in parsed.transactions], f, indent=2)
            except Exception:
                pass
            return parsed.transactions
        except Exception:
            pass

    return []


def _build_payload_for_statement(stmt: StatementRecord) -> ExportPayload:
    """Builds an ExportPayload from a StatementRecord."""
    txs = _get_statement_transactions(stmt)

    start_bal = stmt.starting_balance or "0.00"
    end_bal = stmt.ending_balance or "0.00"

    rec_summary, _ = reconcile_statement(start_bal, end_bal, txs)

    metadata = StatementMetadata(
        bank_name=stmt.bank_name or "Statement Bank",
        account_number=stmt.id,
        statement_period_start=stmt.statement_period_start or "2026-01-01",
        statement_period_end=stmt.statement_period_end or "2026-01-31",
        starting_balance=start_bal,
        ending_balance=end_bal,
        currency="USD",
        page_count=stmt.page_count or 1,
    )

    return ExportPayload(
        metadata=metadata,
        reconciliation=rec_summary,
        transactions=txs,
    )


def _format_response(file_bytes: bytes, format_type: str, base_filename: str = "statement") -> Response:
    """Creates a downloadable FastAPI Response with appropriate Content-Type and headers."""
    fmt = format_type.lower().strip(".")
    if fmt == "csv":
        return Response(
            content=file_bytes,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base_filename}.csv"'},
        )
    elif fmt in ("xlsx", "excel"):
        return Response(
            content=file_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{base_filename}.xlsx"'},
        )
    elif fmt == "json":
        return Response(
            content=file_bytes,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{base_filename}.json"'},
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format '{format_type}'. Supported formats: csv, xlsx, json",
        )


# ---------------------------------------------------------------------------
# Programmatic Verification Endpoint
# ---------------------------------------------------------------------------

@router.post("/verify/{format_type}")
def verify_export_endpoint(
    format_type: str,
    payload: ExportPayload,
):
    """
    Validates round-trip fidelity: Ingest(Export(S)) == S.
    """
    fmt = format_type.lower().strip(".")
    if fmt == "csv":
        exported = export_to_csv(payload)
    elif fmt in ("xlsx", "excel"):
        exported = export_to_xlsx(payload)
    elif fmt == "json":
        exported = export_to_json(payload)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format '{format_type}'")

    is_valid, msg = verify_round_trip(exported, fmt, payload)
    return {
        "valid": is_valid,
        "format": fmt,
        "message": msg,
    }


# ---------------------------------------------------------------------------
# Direct Payload Export Endpoints
# ---------------------------------------------------------------------------

@router.post("/{format_type}")
def export_payload_direct(
    format_type: str,
    payload: ExportPayload,
):
    """
    Exports a submitted ExportPayload directly to CSV, XLSX, or JSON.
    Used by client SDKs, testing harnesses, and in-memory export previews.
    """
    fmt = format_type.lower().strip(".")
    if fmt == "csv":
        data = export_to_csv(payload)
    elif fmt in ("xlsx", "excel"):
        data = export_to_xlsx(payload)
    elif fmt == "json":
        data = export_to_json(payload)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid format '{format_type}'. Expected 'csv', 'xlsx', or 'json'.",
        )

    return _format_response(data, fmt, base_filename="statement_export")


# ---------------------------------------------------------------------------
# Statement Record Export Endpoints
# ---------------------------------------------------------------------------

@router.get("/{statement_id}/{format_type}")
@router.post("/{statement_id}/{format_type}")
def export_statement(
    statement_id: str,
    format_type: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Exports an existing stored statement by ID into CSV, XLSX, or JSON.
    Scoping: Enforces tenant isolation if user is authenticated.
    """
    query = db.query(StatementRecord).filter(StatementRecord.id == statement_id)
    if current_user:
        query = query.filter(StatementRecord.tenant_id == current_user.tenant_id)

    stmt = query.first()
    if not stmt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Statement '{statement_id}' not found.",
        )

    payload = _build_payload_for_statement(stmt)
    fmt = format_type.lower().strip(".")

    if fmt == "csv":
        data = export_to_csv(payload)
    elif fmt in ("xlsx", "excel"):
        data = export_to_xlsx(payload)
    elif fmt == "json":
        data = export_to_json(payload)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid export format '{format_type}'.",
        )

    base_name = os.path.splitext(stmt.filename)[0] or statement_id
    return _format_response(data, fmt, base_filename=f"{base_name}_export")

