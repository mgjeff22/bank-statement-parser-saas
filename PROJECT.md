# Project: AI Bank Statement Parser Micro-SaaS

## Architecture

The system is a production-grade, full-stack micro-SaaS application designed for automated multimodal bank statement extraction, mathematical reconciliation, interactive transaction editing, multi-format exports, and tiered subscription billing.

```
                           ┌───────────────────────────────────────────────────────────┐
                           │                     Frontend (React + Vite)               │
                           │  - Multi-Tenant Auth (Login / Register / Profile)         │
                           │  - SaaS Dashboard (Usage Meters, Statement History)       │
                           │  - Split-Pane Workspace (Doc Viewer + Editable Grid)      │
                           │  - Real-Time Reconciliation Banner (Net Cashflow / Alert) │
                           │  - Multi-Format Exporter UI (CSV, XLSX, JSON)             │
                           │  - Billing Portal & Mock Billing Controls                 │
                           └─────────────────────────────┬─────────────────────────────┘
                                                         │ REST API (JSON / Multipart)
                                                         ▼
                           ┌───────────────────────────────────────────────────────────┐
                           │                   Backend (FastAPI / Node)                │
                           │                                                           │
                           │  [Auth & Tenant Middleware] ─── [Quota Enforcement Guard] │
                           │                         │                                 │
                           │                         ▼                                 │
                           │          [Statement Ingestion Controller]                 │
                           │                         │                                 │
                           │                         ▼                                 │
                           │        [Multimodal Parsing Pipeline Router]               │
                           │        ├── Digital PDF: pdfplumber / pypdf                │
                           │        ├── Scanned PDF: pypdfium2 (300 DPI)               │
                           │        ├── Raster Images: OpenCV Preprocessing            │
                           │        ├── OCR Engine: RapidOCR (CPU ONNX)                │
                           │        └── AI Vision Fallback: Gemini 2.0 Flash           │
                           │                         │                                 │
                           │                         ▼                                 │
                           │       [Deterministic Decimal Reconciliation Engine]       │
                           │       ├── Start + Credits - Debits == End Balance         │
                           │       ├── Row-by-Row Running Balance Verification         │
                           │       └── Anomaly & Discrepancy Diagnostics               │
                           │                         │                                 │
                           │                         ▼                                 │
                           │       [Exporter Engine: RFC 4180 CSV, Styled XLSX, JSON]  │
                           │                         │                                 │
                           │                         ▼                                 │
                           │       [Billing Engine: Stripe Live + Mock Adapter]        │
                           │       ├── Checkout & Customer Portal                      │
                           │       └── Idempotent Webhook Lifecycle State Machine      │
                           └─────────────────────────────┬─────────────────────────────┘
                                                         │
                                                         ▼
                                       ┌───────────────────────────────────┐
                                       │        Storage & Persistence      │
                                       │  - SQLite (ACID, Tenant Scoped)   │
                                       │  - File Storage (Encrypted/Local) │
                                       └───────────────────────────────────┘
```

## Feature Inventory

Every feature identified in the Survey phase is mapped to an implementation milestone below:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Document Format Router | Automatic classifier distinguishing digital vector PDFs, scanned/image PDFs, and raster images (PNG, JPEG, WebP) | M1 | survey_explorer_1 |
| 2 | Digital PDF Table Extractor | Deterministic spatial extraction for digital PDFs preserving tables, columns, and line wraps | M1 | survey_explorer_1 |
| 3 | Scanned PDF Rasterizer | High-resolution 300 DPI PDF rendering via Google PDFium (zero external Poppler binary dependency) | M1 | survey_explorer_1 |
| 4 | Image Preprocessing Pipeline | Grayscale conversion, adaptive contrast enhancement (CLAHE), deskewing, and binarization | M1 | survey_explorer_1 |
| 5 | Local OCR Engine | 100% self-contained local CPU ONNX OCR via RapidOCR (zero external Tesseract binary dependency) | M1 | survey_explorer_1 |
| 6 | Multimodal Vision Fallback | Gemini 2.0 Flash vision extraction fallback for heavily degraded or non-standard statements | M1 | survey_explorer_1 |
| 7 | Transaction Record Normalizer | Structured extraction of Date (ISO-8601), Payee/Description, Debit/Credit type, Amount, Category, Running Balance | M1 | survey_explorer_1 |
| 8 | Statement Metadata Extractor | Extraction of Bank Name, Account Number, Statement Period, Starting Balance, Ending Balance | M1 | survey_explorer_1 |
| 9 | Decimal Reconciliation Formula | Exact arbitrary-precision decimal verification: Starting + Credits - Debits == Ending Balance | M1 | survey_explorer_1 |
| 10 | Net Cashflow Calculation | Net Cashflow computation: Total Credits - Total Debits | M1 | survey_explorer_1 |
| 11 | Sequential Running Balance Check | Step-by-step row running balance check: Prior Balance +/- Amount == Current Running Balance | M1 | survey_explorer_1 |
| 12 | Discrepancy Diagnostic Rules | Automated detection of Sign Inversion ($|\Delta|/2$), Missing Transaction Gaps, Out-of-Order Dates, and Transposition Errors | M1 | survey_explorer_1 |
| 13 | Synthetic Statement Fixture Generator | Programmatic generator creating digital PDFs, scanned PDFs, images, and ground-truth JSON fixtures | M1 | survey_explorer_1 |
| 14 | Secure Authentication System | Argon2id/bcrypt password hashing, JWT/session authentication, login, registration, and logout | M2 | survey_explorer_3 |
| 15 | Multi-Tenant Data Isolation | Tenant IDs on all models, query scoping middleware preventing cross-tenant data access | M2 | survey_explorer_3 |
| 16 | Tiered Subscription Quota Engine | Quota configuration (Free: 5 pgs, Starter: 50 pgs, Pro: 500 pgs) with atomic SQL decrement and HTTP 402 blocking | M2 | survey_spec_miner_2 |
| 17 | SaaS User Dashboard | Visual monthly page consumption meter against subscription quota, upgrade warnings | M2 | survey_explorer_3 |
| 18 | Statement Upload History & Lifecycle | History table with live status badges (`queued`, `processing`, `completed`, `error`), file download & delete | M2 | survey_explorer_3 |
| 19 | Multi-Subsystem Health Endpoint | `/api/health` endpoint validating Database, Storage, Parsing Pipeline, and Billing Adapter readiness | M2 | survey_explorer_3 |
| 20 | Stripe Checkout Session Integration | Monthly & annual Stripe checkout session creation, price tier mapping, customer linking | M3 | survey_spec_miner_2 |
| 21 | Stripe Customer Portal Integration | Self-service billing portal session generation for managing payment methods and cancelations | M3 | survey_spec_miner_2 |
| 22 | Idempotent Webhook Handler | Webhook signature verification and DB-level deduplication table (`processed_stripe_events`) | M3 | survey_spec_miner_2 |
| 23 | Webhook Lifecycle State Machine | Handlers for `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_succeeded`, `invoice.payment_failed` | M3 | survey_spec_miner_2 |
| 24 | Zero-Config Mock Billing Adapter | Toggleable mock billing mode (`BILLING_MODE=mock`), simulated checkout, simulated portal, and test webhook trigger | M3 | survey_spec_miner_2 |
| 25 | Split-Pane Inspection Workspace UI | Side-by-side view: Document viewer (PDF/Image with zoom/pan/page nav) alongside editable transaction grid | M4 | survey_explorer_3 |
| 26 | Inline Editable Transaction Grid | Interactive table with inline cell edits (Date, Payee, Type, Amount, Category), search, sorting, filtering | M4 | survey_explorer_3 |
| 27 | Dynamic Row Management UI | Ability to add custom transaction rows, delete rows, and re-order entries | M4 | survey_explorer_3 |
| 28 | Real-Time Reconciliation Banner UI | Interactive header re-computing Net Cashflow, Ending Balance, and Discrepancy on any edit with visual status alerts | M4 | survey_explorer_3 |
| 29 | Anomaly Highlighting & Resolution UI | Row-level anomaly indicators (Sign Inversion, Balance Gap) with one-click quick-fix actions | M4 | survey_explorer_3 |
| 30 | RFC 4180 CSV Exporter | UTF-8 BOM, standard escaping, valid headers, formatted amounts | M4 | survey_explorer_3 |
| 31 | Professional Excel (.xlsx) Exporter | Styled headers, typed dates, numeric currency format `$#,##0.00`, dynamic `=SUM()` formulas, Reconciliation Summary sheet | M4 | survey_explorer_3 |
| 32 | Structured JSON Exporter | Versioned hierarchical JSON containing statement metadata, reconciliation summary, and transaction array | M4 | survey_explorer_3 |
| 33 | Exporter Round-Trip Verification | Automated programmatic round-trip test asserting $Ingest(Export(S)) == S$ with zero schema corruption | M4 | survey_explorer_3 |
| 34 | E2E Test Suite (Tiers 1-4) | Opaque-box test suite covering feature coverage, boundaries, pairwise combinations, and real-world workloads | M-E2E / M5 | ORIGINAL_REQUEST |
| 35 | Tier 5 Adversarial Hardening | White-box stress-testing, boundary probing, and forensic integrity audit verification | M5 | ORIGINAL_REQUEST |

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M-E2E | E2E Testing Suite (Tiers 1-4) | Synthetic statement generator, test harness, Tiers 1-4 requirement-driven opaque-box tests, TEST_READY.md | none | DONE |
| M1 | Multimodal Statement Parsing & Reconciliation Engine | Core ingestion, PDF/Image OCR, normalization, strict Decimal reconciliation, anomaly diagnostics (Features 1-13) | none | DONE |
| M2 | Multi-Tenant Auth, User Dashboard & Quota Metering | User authentication, tenant isolation, database models, quota tracking middleware, dashboard APIs, /api/health (Features 14-19) | none | DONE |
| M3 | Stripe Billing & Mock Billing Integration | Stripe checkout, customer portal, idempotent webhooks, zero-config mock adapter (Features 20-24) | M2 | DONE |
| M4 | Interactive Transaction Workspace & Exporter Engine | Split-pane workspace UI, editable grid, real-time reconciliation banner, CSV/XLSX/JSON exporters with round-trip test (Features 25-33) | M1, M2 | DONE |
| M5 | Final Milestone: 100% E2E Test Pass & Adversarial Hardening | Pass 100% of E2E test suite (Tiers 1-4), Tier 5 adversarial hardening with Challengers, Forensic Audit verification | M-E2E, M1, M2, M3, M4 | DONE |

## Interface Contracts

### Parser Engine ↔ Workspace & Database
```typescript
interface StatementMetadata {
  bank_name: string;
  account_number: string;
  statement_period_start: string; // ISO-8601 YYYY-MM-DD
  statement_period_end: string;   // ISO-8601 YYYY-MM-DD
  starting_balance: string;       // Exact Decimal string e.g. "1250.00"
  ending_balance: string;         // Exact Decimal string e.g. "3450.75"
  currency: string;               // ISO-4217 e.g. "USD"
}

interface TransactionRecord {
  id: string;
  date: string;                   // ISO-8601 YYYY-MM-DD
  payee: string;
  type: "debit" | "credit";
  amount: string;                 // Exact Decimal string e.g. "124.50"
  category: string;
  running_balance: string;        // Exact Decimal string e.g. "2125.50"
  has_anomaly: boolean;
  anomaly_type?: "SIGN_INVERSION" | "MISSING_GAP" | "OUT_OF_ORDER_DATE" | "TRANSPOSITION";
}

interface ReconciliationSummary {
  starting_balance: string;
  total_credits: string;
  total_debits: string;
  net_cashflow: string;           // credits - debits
  calculated_ending_balance: string; // starting + credits - debits
  reported_ending_balance: string;
  discrepancy: string;            // calculated - reported
  is_reconciled: boolean;         // discrepancy == "0.00"
  diagnostic_flags: string[];
}
```

### Billing & Quota Guard ↔ Upload Controller
```typescript
interface QuotaCheckResult {
  allowed: boolean;
  tier: "free" | "starter" | "pro";
  pages_used: number;
  monthly_limit: number;
  remaining_pages: number;
  error_code?: "QUOTA_EXCEEDED";
}
```

### Exporter Engine Contracts
```typescript
interface ExportPayload {
  metadata: StatementMetadata;
  reconciliation: ReconciliationSummary;
  transactions: TransactionRecord[];
}
```

## Code Layout

```
bank_statement_parser/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth.py              # User authentication endpoints
│   │   │   ├── dashboard.py         # SaaS dashboard stats & upload history
│   │   │   ├── statements.py        # Statement upload & parsing trigger
│   │   │   ├── transactions.py      # Transaction CRUD & batch updates
│   │   │   ├── export.py            # CSV, XLSX, JSON download endpoints
│   │   │   ├── billing.py           # Stripe checkout, portal, webhooks, mock endpoints
│   │   │   └── health.py            # /api/health multi-system status
│   │   ├── core/
│   │   │   ├── config.py            # Environment & app configuration
│   │   │   ├── security.py          # Password hashing & JWT tokens
│   │   │   └── database.py          # SQLite engine & session management
│   │   ├── models/                  # SQLAlchemy database entities (user, tenant, subscription, quota, statement, billing)
│   │   ├── schemas/                 # Pydantic v2 data transfer schemas
│   │   ├── services/
│   │   │   ├── parser/              # Router, digital_pdf, ocr_engine, normalizer, vision_ai
│   │   │   ├── reconciliation.py    # Strict Decimal reconciliation logic
│   │   │   ├── exporter.py          # CSV, openpyxl XLSX, JSON exporter
│   │   │   ├── quota.py             # Atomic quota meter & tier gates
│   │   │   └── billing/             # Stripe live & zero-config mock adapters
│   │   └── main.py                  # FastAPI application entrypoint (serves frontend static SPA)
│   ├── tests/                       # 123 unit, adversarial & integration tests
│   └── pyproject.toml               # Python dependencies (uv-managed)
├── frontend/                        # Modern React + Vite + Tailwind CSS application
│   ├── src/
│   │   ├── api/                     # API client for backend
│   │   ├── components/              # Auth, Dashboard, Workspace (SplitPane), Billing
│   │   ├── App.tsx                  # Router & navigation layout
│   │   └── main.tsx                 # React entrypoint
│   ├── dist/                        # Production build assets
│   ├── package.json
│   └── vite.config.ts
├── tests_e2e/                       # E2E Testing Suite (200 test cases across Tiers 1-5)
│   ├── fixtures/                    # 15 synthetic statements (PDF, PNG, JPG) + 15 ground-truth JSONs
│   ├── generators/                  # ReportLab synthetic PDF/Image generator
│   ├── harness/                     # OpaqueSaaSClient, contracts, oracle, reporter
│   ├── tier1_features/              # Features 1-35 coverage (>=5 tests per feature)
│   ├── tier2_boundaries/            # Boundary & corner cases
│   ├── tier3_interactions/          # Cross-feature pairwise tests
│   ├── tier4_workloads/             # Realistic multi-statement workload tests
│   └── run_e2e.py                   # E2E test runner
├── TEST_INFRA.md                    # E2E test infrastructure specification
├── TEST_READY.md                    # E2E test suite certification (200/200 passing)
└── PROJECT.md                       # Global project blueprint
```
