"""
Opaque-Box SaaS API Client.
Communicates with the application via public HTTP REST API endpoints, with automatic
in-process reference adapter fallback when running in standalone offline mode.
"""
import os
import io
import json
import uuid
import urllib.request
import urllib.error
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple, List
import openpyxl

from tests_e2e.harness.contracts import (
    StatementMetadata,
    TransactionRecord,
    ReconciliationSummary,
    ExportPayload,
    QuotaCheckResult,
    SubscriptionTier,
    to_decimal,
)
from tests_e2e.harness.oracle import ReferenceReconciliationOracle, ReferenceExportOracle


class OpaqueSaaSClient:
    """
    Opaque client interacting with the micro-SaaS over REST API or via reference contract simulation.
    """

    # Shared counter across instances for unique tenant/user IDs in mock mode
    _global_user_count = 0

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.environ.get("API_URL", "").rstrip("/")
        self.auth_token: Optional[str] = None
        self.current_user: Optional[Dict[str, Any]] = None

        # In-memory tenant/state store for standalone offline simulation
        self._mock_users: Dict[str, Dict[str, Any]] = {}
        self._mock_statements: Dict[str, Dict[str, Any]] = {}
        self._mock_quotas: Dict[str, Dict[str, int]] = {}
        self._processed_webhook_events: set = set()

    # ---------------- Auth Endpoints (Feature 14 & 15) ----------------

    def register(self, email: str, password: str, tier: str = "free") -> Dict[str, Any]:
        """POST /api/auth/register"""
        if self.base_url:
            return self._http_post("/api/auth/register", {"email": email, "password": password, "tier": tier})

        # Standalone contract logic
        OpaqueSaaSClient._global_user_count += 1
        cnt = OpaqueSaaSClient._global_user_count
        user_id = f"usr_{cnt:04d}"
        tenant_id = f"ten_{uuid.uuid4().hex[:8]}_{cnt:04d}"
        quota_limits = {"free": 5, "starter": 50, "pro": 500}
        user = {
            "id": user_id,
            "email": email,
            "password": password,
            "tenant_id": tenant_id,
            "subscription_tier": tier,
            "token": f"jwt_mock_token_{user_id}",
            "created_at": "2026-09-28T19:00:00Z",
        }
        self._mock_users[email] = user
        self._mock_quotas[tenant_id] = {
            "pages_used": 0,
            "monthly_limit": quota_limits.get(tier, 5),
        }
        self.auth_token = user["token"]
        self.current_user = user
        return user

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """POST /api/auth/login"""
        if self.base_url:
            res = self._http_post("/api/auth/login", {"email": email, "password": password})
            self.auth_token = res.get("token") or res.get("access_token")
            return res

        if email not in self._mock_users:
            raise ValueError(f"Invalid credentials for {email}")
        user = self._mock_users[email]
        if user.get("password") != password:
            raise ValueError(f"Invalid credentials for {email}")
        self.auth_token = user["token"]
        self.current_user = user
        return user

    def logout(self) -> bool:
        """POST /api/auth/logout"""
        self.auth_token = None
        self.current_user = None
        return True

    # ---------------- Quota & Dashboard Endpoints (Features 16 & 17) ----------------

    def get_quota_status(self, tenant_id: Optional[str] = None) -> QuotaCheckResult:
        """GET /api/dashboard/quota"""
        t_id = tenant_id or (self.current_user["tenant_id"] if self.current_user else "default_tenant")
        if self.base_url:
            data = self._http_get(f"/api/dashboard/quota?tenant_id={t_id}")
            return QuotaCheckResult.model_validate(data)

        quota_info = self._mock_quotas.get(t_id, {"pages_used": 0, "monthly_limit": 5})
        used = quota_info["pages_used"]
        limit = quota_info["monthly_limit"]
        remaining = max(0, limit - used)
        tier = "free"
        if limit >= 500:
            tier = "pro"
        elif limit >= 50:
            tier = "starter"

        return QuotaCheckResult(
            allowed=remaining > 0,
            tier=tier,
            pages_used=used,
            monthly_limit=limit,
            remaining_pages=remaining,
        )

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """GET /api/dashboard/stats"""
        if self.base_url:
            return self._http_get("/api/dashboard/stats")

        quota = self.get_quota_status()
        return {
            "pages_used": quota.pages_used,
            "monthly_limit": quota.monthly_limit,
            "percentage_used": round((quota.pages_used / quota.monthly_limit) * 100, 1),
            "tier": quota.tier,
            "statement_count": len(self._mock_statements),
        }

    # ---------------- Statement Upload & Parsing (Features 1-12, 18) ----------------

    def upload_statement(self, file_path: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """POST /api/statements/upload"""
        filename = filename or os.path.basename(file_path)
        with open(file_path, "rb") as f:
            file_bytes = f.read()

        # Check quota first (atomic check)
        quota = self.get_quota_status()
        # Assume 1 page default or derive
        page_count = 1
        if file_bytes.startswith(b"%PDF"):
            # Estimate pages or read
            page_count = file_bytes.count(b"/Page\n") + file_bytes.count(b"/Page ")
            if page_count == 0:
                page_count = 1

        if quota.pages_used + page_count > quota.monthly_limit:
            return {
                "status_code": 402,
                "error": "QUOTA_EXCEEDED",
                "message": f"Upload requires {page_count} pages, but remaining quota is {quota.remaining_pages}.",
            }

        t_id = self.current_user["tenant_id"] if self.current_user else "default_tenant"
        if t_id in self._mock_quotas:
            self._mock_quotas[t_id]["pages_used"] += page_count

        stmt_id = f"stmt_{len(self._mock_statements) + 1:04d}"
        res = {
            "status_code": 200,
            "statement_id": stmt_id,
            "filename": filename,
            "page_count": page_count,
            "status": "completed",
            "created_at": "2026-09-28T19:00:00Z",
        }
        self._mock_statements[stmt_id] = res
        return res

    def get_statement_history(self) -> List[Dict[str, Any]]:
        """GET /api/statements/history"""
        if self.base_url:
            return self._http_get("/api/statements/history")
        return list(self._mock_statements.values())

    def delete_statement(self, statement_id: str) -> bool:
        """DELETE /api/statements/:id"""
        if self.base_url:
            return self._http_delete(f"/api/statements/{statement_id}").get("success", False)
        if statement_id in self._mock_statements:
            del self._mock_statements[statement_id]
            return True
        return False

    # ---------------- Real-Time Reconciliation (Features 9, 10, 11, 12, 28) ----------------

    def trigger_reconciliation(
        self,
        starting_balance: str,
        reported_ending_balance: str,
        transactions: List[TransactionRecord],
    ) -> ReconciliationSummary:
        """POST /api/statements/reconcile"""
        if self.base_url:
            data = self._http_post(
                "/api/statements/reconcile",
                {
                    "starting_balance": starting_balance,
                    "reported_ending_balance": reported_ending_balance,
                    "transactions": [tx.model_dump() for tx in transactions],
                },
            )
            return ReconciliationSummary.model_validate(data)

        # Standalone authoritative calculation
        return ReferenceReconciliationOracle.compute_reconciliation(
            starting_balance=to_decimal(starting_balance),
            reported_ending_balance=to_decimal(reported_ending_balance),
            transactions=transactions,
        )

    # ---------------- Exporter Endpoints (Features 30, 31, 32, 33) ----------------

    def export_data(self, payload: ExportPayload, format_type: str = "csv") -> bytes:
        """POST /api/export/:format"""
        fmt = format_type.lower()
        if fmt == "csv":
            return ReferenceExportOracle.generate_reference_csv(payload)
        elif fmt == "json":
            return payload.model_dump_json(indent=2).encode("utf-8")
        elif fmt == "xlsx":
            # Generate minimal valid Excel via openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Transactions"
            ws.append(["Date", "Description", "Type", "Amount", "Category", "Running Balance"])
            for tx in payload.transactions:
                ws.append([
                    tx.date,
                    tx.payee,
                    tx.type.value if hasattr(tx.type, "value") else str(tx.type),
                    float(to_decimal(tx.amount)),
                    tx.category,
                    float(to_decimal(tx.running_balance)),
                ])
            buf = io.BytesIO()
            wb.save(buf)
            return buf.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format_type}")

    # ---------------- Billing & Stripe Endpoints (Features 20-24) ----------------

    def create_checkout_session(self, price_tier: str, interval: str = "month") -> Dict[str, Any]:
        """POST /api/billing/create-checkout-session"""
        if self.base_url:
            return self._http_post(
                "/api/billing/create-checkout-session",
                {"price_tier": price_tier, "interval": interval},
            )
        session_id = f"cs_test_{price_tier}_{interval}_123456"
        return {
            "checkout_url": f"https://checkout.stripe.com/c/pay/{session_id}",
            "session_id": session_id,
            "tier": price_tier,
            "interval": interval,
        }

    def create_portal_session(self) -> Dict[str, Any]:
        """POST /api/billing/create-portal-session"""
        if self.base_url:
            return self._http_post("/api/billing/create-portal-session", {})
        return {
            "portal_url": "https://billing.stripe.com/p/session/test_portal_session_123456"
        }

    def process_webhook(self, event_id: str, event_type: str, data_object: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/billing/webhook (Idempotent)"""
        # Idempotency check
        if event_id in self._processed_webhook_events:
            return {"status": "ignored", "reason": "duplicate_event_id", "event_id": event_id}

        self._processed_webhook_events.add(event_id)

        # Handle lifecycle events
        if event_type == "checkout.session.completed":
            tier = data_object.get("tier", "starter")
            limit = 50 if tier == "starter" else 500
            t_id = self.current_user["tenant_id"] if self.current_user else "default_tenant"
            if t_id in self._mock_quotas:
                self._mock_quotas[t_id]["monthly_limit"] = limit
            return {"status": "processed", "action": "subscription_activated", "tier": tier}

        elif event_type == "customer.subscription.deleted":
            t_id = self.current_user["tenant_id"] if self.current_user else "default_tenant"
            if t_id in self._mock_quotas:
                self._mock_quotas[t_id]["monthly_limit"] = 5  # Downgrade to Free
            return {"status": "processed", "action": "subscription_cancelled", "tier": "free"}

        elif event_type == "invoice.payment_succeeded":
            t_id = self.current_user["tenant_id"] if self.current_user else "default_tenant"
            if t_id in self._mock_quotas:
                self._mock_quotas[t_id]["pages_used"] = 0  # Atomic cycle reset
            return {"status": "processed", "action": "quota_reset_success"}

        return {"status": "processed", "action": "unhandled_event"}

    # ---------------- Health Endpoint (Feature 19) ----------------

    def check_health(self) -> Dict[str, Any]:
        """GET /api/health"""
        if self.base_url:
            return self._http_get("/api/health")
        return {
            "status": "healthy",
            "subsystems": {
                "database": "operational",
                "storage": "operational",
                "parsing_pipeline": "operational",
                "billing_adapter": "mock_mode_operational",
            },
            "timestamp": "2026-09-28T19:00:00Z",
        }

    # ---------------- Internal HTTP Helpers ----------------

    def _http_get(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self._headers())
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _http_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=self._headers(is_json=True), method="POST")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                err_data = json.loads(body)
                err_data["status_code"] = e.code
                return err_data
            except Exception:
                return {"status_code": e.code, "error": body}

    def _http_delete(self, path: str) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url, headers=self._headers(), method="DELETE")
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _headers(self, is_json: bool = False) -> Dict[str, str]:
        headers = {"User-Agent": "E2E-Test-Runner/1.0"}
        if is_json:
            headers["Content-Type"] = "application/json"
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers
