# E2E Test Infrastructure Specification: AI Bank Statement Parser Micro-SaaS

## 1. Test Philosophy & Opaque-Box Principles

The End-to-End (E2E) Test Suite for the **AI Bank Statement Parser Micro-SaaS** is strictly **opaque-box**, **requirement-driven**, and **independent of internal module implementation details**. 

### 1.1 Core Principles
1. **Opaque-Box Boundary**:
   Tests interact with the system solely through documented public interfaces:
   - Public REST API HTTP endpoints (e.g., `/api/auth/*`, `/api/statements/*`, `/api/billing/*`, `/api/export/*`, `/api/health`).
   - Domain Interface Contracts and Schema Specifications (defined in `PROJECT.md § Interface Contracts`).
   - Standard persistent artifacts: RFC 4180 CSV files, Microsoft Excel `.xlsx` workbooks, and structured JSON files.
   - Ground-truth synthetic statements (vector PDFs, scanned PDFs, PNG/JPEG/WebP images).
   Tests treat the internal code as an opaque black box. No test relies on private class methods, internal variables, or non-contractual state.

2. **Requirement-Driven from `ORIGINAL_REQUEST.md`**:
   Every test traces directly back to the four foundational requirements:
   - **R1: Multimodal Bank Statement Parsing & Reconciliation Engine** (digital/scanned PDFs, images, transaction extraction, strict decimal reconciliation, anomaly diagnostics).
   - **R2: Interactive Transaction Workspace & Exporter** (viewing, editing, adding/deleting rows, CSV, styled XLSX with formulas, JSON export with round-trip verification).
   - **R3: Subscription Management, Stripe Billing & Quota Metering** (tiered limits, Stripe checkout & customer portal, idempotent webhook state machine, zero-config mock billing adapter).
   - **R4: Multi-Tenant SaaS Dashboard & Authentication** (secure auth, tenant isolation, quota consumption meters, upload lifecycle, multi-subsystem health checks).

3. **Deterministic Mathematical Correctness**:
   Financial reconciliation is mathematically absolute. All tests enforce arbitrary-precision fixed-point decimal arithmetic (`Decimal('0.01')`). Any floating-point drift or cent rounding discrepancy triggers an immediate test failure.

4. **Progressive Testability & Self-Sufficiency**:
   The E2E test harness functions in dual execution modes:
   - **Standalone Contract & Reference Mode**: When backend services are not yet launched or during milestone unit validation, tests run against the authoritative Reference Oracle and contract schemas.
   - **Live Integration Mode**: When `API_URL` is configured, tests execute HTTP requests against the live running backend server.

---

## 2. Feature Inventory & Test Mapping (100% Coverage of All 35 Features)

Every feature defined in `PROJECT.md § Feature Inventory` is mapped to specific test cases across the 4 test tiers:

| # | Feature Name | Tier 1 Test Suite | Tier 2 Boundaries | Tier 3 Interactions | Tier 4 Workloads |
|---|--------------|-------------------|-------------------|---------------------|------------------|
| 1 | Document Format Router | `test_f01_f06_document_pipeline.py::test_router_*` | File ext, MIME types, corrupted headers | Router + Preprocessor | Multi-statement batch |
| 2 | Digital PDF Table Extractor | `test_f01_f06_document_pipeline.py::test_digital_pdf_*` | Multi-line wrapped text, column alignment | PDF Extractor + Normalizer | Chase Business 4-page |
| 3 | Scanned PDF Rasterizer | `test_f01_f06_document_pipeline.py::test_rasterizer_*` | 300 DPI scaling, multi-page raster | Rasterizer + OCR | Scanned multi-page flow |
| 4 | Image Preprocessing Pipeline | `test_f01_f06_document_pipeline.py::test_image_prep_*` | Skew angle ($\pm 5^\circ$), low contrast, noise | Preprocessing + OCR | Degraded phone photo |
| 5 | Local OCR Engine | `test_f01_f06_document_pipeline.py::test_ocr_engine_*` | Low resolution, dense font, blur | OCR + Table Builder | Scanned statement parse |
| 6 | Multimodal Vision Fallback | `test_f01_f06_document_pipeline.py::test_vision_fallback_*`| Degraded text, handwritten notes | OCR failure -> Vision fallback | Degraded statement |
| 7 | Transaction Record Normalizer | `test_f07_f13_parsing_reconciliation.py::test_normalizer_*`| US vs EU date formats, currency symbols | Normalizer + Reconciliation | High-volume normalizer |
| 8 | Statement Metadata Extractor | `test_f07_f13_parsing_reconciliation.py::test_metadata_*` | Masked accts, missing header, date ranges | Metadata + Quota | Chase & BoA statements |
| 9 | Decimal Reconciliation Formula | `test_f07_f13_parsing_reconciliation.py::test_formula_*` | $0.1 + 0.2 \neq 0.3$ float drift, penny errors | Formula + Anomaly Engine | Wells Fargo mismatch |
| 10 | Net Cashflow Calculation | `test_f07_f13_parsing_reconciliation.py::test_cashflow_*` | Zero net cashflow, negative cashflow | Cashflow + Dashboard | BoA checking statement |
| 11 | Sequential Running Balance Check | `test_f07_f13_parsing_reconciliation.py::test_running_bal_*`| Missing row gap, step-by-step jump | Running Bal + Diagnostics | Multi-page balance chain |
| 12 | Discrepancy Diagnostic Rules | `test_f07_f13_parsing_reconciliation.py::test_diagnostics_*`| Sign inversion ($\|\Delta\|/2$), Transposition | Diagnostics + Quick-Fix | Deliberate anomaly fixes |
| 13 | Synthetic Statement Generator | `test_f07_f13_parsing_reconciliation.py::test_generator_*`| Anomaly injection, vector vs raster | Generator + Fixtures | 15 synthetic statements |
| 14 | Secure Authentication System | `test_f14_f19_auth_quota_dashboard.py::test_auth_*` | Password entropy, expired JWT, invalid auth | Auth + Tenant Isolation | User registration flow |
| 15 | Multi-Tenant Data Isolation | `test_f14_f19_auth_quota_dashboard.py::test_tenant_*` | Cross-tenant access attempt, ID tampering | Tenant + Statement Store | Multi-user isolation |
| 16 | Tiered Subscription Quota Engine| `test_f14_f19_auth_quota_dashboard.py::test_quota_*` | Exact limit (5/50/500), 1-page overflow | Quota + Mock Billing | Freelance batch quota |
| 17 | SaaS User Dashboard | `test_f14_f19_auth_quota_dashboard.py::test_dashboard_*`| 0% usage, 99% usage, 100% usage | Dashboard + Upload history | User lifecycle flow |
| 18 | Statement Upload History & Lifecycle | `test_f14_f19_auth_quota_dashboard.py::test_history_*` | Status transitions (`queued`->`completed`)| History + File Deletion | Complete history review |
| 19 | Multi-Subsystem Health Endpoint | `test_f14_f19_auth_quota_dashboard.py::test_health_*` | DB down, storage down, healthy status | Health + Billing Adapter | System pre-flight check |
| 20 | Stripe Checkout Session Integration | `test_f20_f24_stripe_billing.py::test_checkout_*` | Monthly vs annual prices, tier selection | Checkout + Webhook | Subscription upgrade flow|
| 21 | Stripe Customer Portal Integration | `test_f20_f24_stripe_billing.py::test_portal_*` | Active subscription vs free tier portal | Portal + Cancel event | Cancellation flow |
| 22 | Idempotent Webhook Handler | `test_f20_f24_stripe_billing.py::test_webhook_idempotency_*`| Duplicate webhook IDs, replay attacks | Webhook + Quota Reset | Duplicate webhook flood |
| 23 | Webhook Lifecycle State Machine | `test_f20_f24_stripe_billing.py::test_lifecycle_*` | `payment_succeeded`, `payment_failed` | State Machine + Quota | Full subscription renewal|
| 24 | Zero-Config Mock Billing Adapter | `test_f20_f24_stripe_billing.py::test_mock_billing_*`| Offline testing without Stripe keys | Mock Adapter + UI | Automated billing test |
| 25 | Split-Pane Inspection Workspace UI | `test_f25_f33_workspace_export.py::test_workspace_layout_*`| Side-by-side doc viewer + grid contracts| Workspace + Edit State | Inspection workflow |
| 26 | Inline Editable Transaction Grid | `test_f25_f33_workspace_export.py::test_grid_edit_*` | Cell edit date, amount, payee, category | Grid Edit + Reconciliation | Manual error resolution |
| 27 | Dynamic Row Management UI | `test_f25_f33_workspace_export.py::test_row_mgmt_*` | Add row, delete row, reorder rows | Row Mgmt + Running Bal | Missing row insertion |
| 28 | Real-Time Reconciliation Banner UI | `test_f25_f33_workspace_export.py::test_banner_*` | Real-time re-compute on edit, color status| Banner + Grid State | Live reconciliation fix|
| 29 | Anomaly Highlighting & Resolution UI | `test_f25_f33_workspace_export.py::test_anomaly_ui_*` | Quick-fix click, sign inversion fix | Anomaly UI + Banner | One-click sign fix |
| 30 | RFC 4180 CSV Exporter | `test_f25_f33_workspace_export.py::test_csv_export_*` | UTF-8 BOM, comma/quote escaping, headers | CSV + Round-Trip Ingest | CSV export verification |
| 31 | Professional Excel (.xlsx) Exporter | `test_f25_f33_workspace_export.py::test_xlsx_export_*`| Formula `=SUM()`, `$#,##0.00`, 2 sheets | XLSX + Data Verification | Excel export check |
| 32 | Structured JSON Exporter | `test_f25_f33_workspace_export.py::test_json_export_*` | Schema validation, Decimal serializing | JSON + API Consumers | JSON export check |
| 33 | Exporter Round-Trip Verification | `test_f25_f33_workspace_export.py::test_roundtrip_*` | Ingest(Export(S)) == S zero corruption | Exporter + Parser Engine | Lossless round-trip |
| 34 | E2E Test Suite (Tiers 1-4) | `run_e2e.py` | Automated runner execution across all tiers | Suite runner orchestration | Full regression run |
| 35 | Tier 5 Adversarial Hardening | `run_e2e.py::verify_adversarial_readiness` | Extreme fuzzing, malformed bytes | Adversarial boundaries | Forensic readiness |

---

## 3. 4-Tier Test Methodology

The test suite is organized into four hierarchical tiers:

### Tier 1: Feature Coverage (Unit & Interface Contract Level)
- **Target**: Every single one of the 35 features must have $\ge 5$ discrete, dedicated test assertions.
- **Coverage**: Representative happy paths, normal operations, basic error paths.
- **Test Count**: $35 \text{ features} \times 5 = 175$ assertions minimum.

### Tier 2: Boundary & Corner Cases
- **Target**: Extreme, edge, and boundary condition verification where edge bugs typically reside.
- **Boundary Dimensions**:
  1. *Numeric Boundaries*: Zero amount transactions ($0.00$), sub-cent values, extreme magnitudes ($100,000,000,000.00$), precision drift checks ($0.1 + 0.2$).
  2. *Temporal Boundaries*: Leap years (posting on Feb 29), year-end rollovers (Dec 31 to Jan 01), date format variations (`MM/DD/YYYY`, `DD/MM/YYYY`, `YYYY-MM-DD`).
  3. *Document Boundaries*: Single transaction statement, 100+ transaction statements, 1-page vs 20-page statements, minimal resolution vs 600 DPI.
  4. *Balance Boundaries*: Negative starting balance, balance dropping below zero (overdraft), negative net cashflow, exactly zero ending balance.
  5. *Visual Distortions*: Rotated scans ($\pm 2.5^\circ, \pm 5.0^\circ$), low contrast, paper shadows, noise.

### Tier 3: Cross-Feature Interactions (Pairwise Combinations)
- **Target**: Interaction defects arising between interconnected micro-SaaS subsystems.
- **Key Interaction Pairs**:
  1. *Quota Limit + Mock Billing*: User hits 5-page Free quota $\rightarrow$ receives HTTP 402 $\rightarrow$ executes Mock Checkout to Starter $\rightarrow$ quota immediately increases to 50 pages $\rightarrow$ retry succeeds.
  2. *Reconciliation Mismatch + Interactive Workspace + Export*: Upload statement with deliberate sign inversion $\rightarrow$ engine flags anomaly $\rightarrow$ user applies quick-fix $\rightarrow$ discrepancy reaches $0.00$ $\rightarrow$ export generates verified CSV/XLSX.
  3. *Multi-Page Scanned PDF + Rasterizer + OCR*: Multi-page scan $\rightarrow$ rendered via PDFium $\rightarrow$ preprocessed $\rightarrow$ OCR extracts tables $\rightarrow$ multi-page running balance chained continuously.
  4. *Stripe Webhook Idempotency + Quota Reset*: Multiple identical `invoice.payment_succeeded` webhook deliveries $\rightarrow$ handled idempotently with single quota credit.
  5. *Multi-Tenant Scoping + History Lifecycle*: Tenant A uploads files $\rightarrow$ Tenant B cannot view, query, or delete Tenant A's statements.

### Tier 4: Real-World Application Workloads
- **Target**: High-fidelity, multi-step user journeys mirroring production micro-SaaS usage.
- **Scenarios**:
  1. **Workload 1: Bank of America Personal Checking**: Vector PDF with mixed direct deposits, debit card purchases, ATM withdrawals, and maintenance fees.
  2. **Workload 2: Chase Commercial Business Multi-Page**: 4-page statement with 40+ transactions, wrapped merchant descriptions, page balance carry-forward.
  3. **Workload 3: Wells Fargo Two-Column with Deliberate Mismatch**: Separate deposit/withdrawal columns, injected missing transaction, automated discrepancy detection, and quick-fix resolution.
  4. **Workload 4: Freelancer Batch Ingestion & Quota Metering**: Uploading 5 monthly statements back-to-back, verifying atomic quota depletion and dashboard update.
  5. **Workload 5: SaaS Subscription Upgrade Lifecycle**: Complete registration, free tier exhaustion, upgrade checkout, customer portal management, and cancellation state transition.

---

## 4. Test Suite Directory Layout

```
bank_statement_parser/
├── tests_e2e/
│   ├── __init__.py
│   ├── pytest.ini                      # Pytest config with markers and paths
│   ├── run_e2e.py                      # Standalone CLI test runner & reporter
│   ├── fixtures/                       # Ground-truth JSONs and generated statement files
│   │   ├── ground_truth/               # Paired reference JSONs (15 authoritative datasets)
│   │   └── statements/                 # Generated PDF, PNG, JPEG, WebP files
│   ├── generators/                     # Programmatic synthetic statement generators
│   │   ├── __init__.py
│   │   ├── statement_generator.py      # ReportLab & PIL generator
│   │   └── fixture_factory.py          # Batch generator for all 15 reference statements
│   ├── harness/                        # Test framework infrastructure
│   │   ├── __init__.py
│   │   ├── client.py                   # Opaque API client with dual live/reference harness
│   │   ├── contracts.py                # Pydantic v2 domain schemas (Statement, Tx, Reconciliation)
│   │   ├── oracle.py                   # Authoritative mathematical reconciliation & export oracle
│   │   └── reporter.py                 # Structured metrics collector and coverage formatter
│   ├── tier1_features/                 # Tier 1: Feature coverage (>=5 tests per feature)
│   │   ├── test_f01_f06_document_pipeline.py
│   │   ├── test_f07_f13_parsing_reconciliation.py
│   │   ├── test_f14_f19_auth_quota_dashboard.py
│   │   ├── test_f20_f24_stripe_billing.py
│   │   └── test_f25_f33_workspace_export.py
│   ├── tier2_boundaries/               # Tier 2: Boundary & corner cases
│   │   ├── test_numeric_boundaries.py
│   │   ├── test_temporal_boundaries.py
│   │   ├── test_document_boundaries.py
│   │   └── test_balance_boundaries.py
│   ├── tier3_interactions/             # Tier 3: Cross-feature pairwise interactions
│   │   ├── test_quota_billing_interactions.py
│   │   ├── test_reconciliation_export_flow.py
│   │   ├── test_multipage_ocr_interaction.py
│   │   └── test_webhook_idempotency_quota.py
│   └── tier4_workloads/                # Tier 4: Realistic end-to-end user workflows
│       ├── test_workload_chase_business.py
│       ├── test_workload_boa_checking.py
│       ├── test_workload_wells_fargo_mismatch.py
│       ├── test_workload_freelancer_batch.py
│       └── test_workload_subscription_upgrade.py
├── TEST_INFRA.md                       # This infrastructure specification
└── TEST_READY.md                       # Signal indicating test suite is ready
```

---

## 5. Execution & Pass/Fail Semantics

### 5.1 Standalone Test Runner (`run_e2e.py`)
Run the entire E2E test suite with the built-in runner:
```bash
uv run --python 3.12 tests_e2e/run_e2e.py
```
Or execute with pytest:
```bash
uv run --python 3.12 -m pytest tests_e2e -v
```

### 5.2 Pass/Fail Criteria
- **Pass (Exit Code 0)**:
  - 100% of test assertions across all 4 tiers pass without unhandled exceptions.
  - Zero floating-point drift in any balance or cashflow calculation.
  - All 15 ground-truth synthetic statements generated and reconciled.
  - Exporter round-trip satisfies $Ingest(Export(S)) == S$ with zero schema drift.
- **Fail (Exit Code 1)**:
  - Any assertion failure in any tier.
  - Any schema validation failure on interface contracts.
  - Any reconciliation discrepancy where ground truth is reconciled, or failure to detect an injected anomaly.
