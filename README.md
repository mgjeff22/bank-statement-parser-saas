# AI Bank Statement Parser (Micro-SaaS)

[![CI & Build Verification](https://img.shields.io/badge/build-passing-brightgreen.svg)](https://github.com/mgjeff22/bank-statement-parser-saas)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![React 18](https://img.shields.io/badge/react-18-61dafb.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)

A production-grade, full-stack **AI Bank Statement Parser Micro-SaaS** application featuring universal multimodal statement extraction (PDF and scanned images), arbitrary-precision decimal balance reconciliation, an interactive split-pane review workspace, and tiered Stripe subscription billing.

---

## Key Features

- **Multimodal Statement Extraction**:
  - Digital PDF parsing via coordinate table extraction (`pdfplumber`).
  - Scanned PDF & image OCR using 300 DPI CPU rasterization (`pypdfium2`), OpenCV contrast/skew preprocessing, and `RapidOCR` ONNX runtime neural text recognition.
  - Zero external system runtime dependencies (no Tesseract or Poppler required).
  - Optional Gemini Vision API multimodal extraction fallback.
- **Arbitrary-Precision Balance Reconciliation**:
  - Strict mathematical verification using Python `decimal.Decimal` ($\text{Starting} + \text{Credits} - \text{Debits} == \text{Ending}$) with $0.00$ float drift.
  - Automated anomaly detection for missing transaction gaps, sign inversions, out-of-order date sequences, and Modulo-9 transposition errors.
- **Interactive Review Workspace (Frontend)**:
  - Responsive split-pane workspace built with React 18, TypeScript, and Tailwind CSS.
  - Side-by-side statement document viewer and interactive transaction data grid.
  - Inline editing, row creation/deletion, search, and category filtering.
  - Real-time balance reconciliation alert banner.
- **Multi-Format Lossless Exporters**:
  - RFC 4180 CSV with UTF-8 Byte Order Mark (BOM) for native Excel compatibility.
  - Formatted Excel (.xlsx via `openpyxl`) with numeric datatypes and formulas.
  - Structured versioned JSON.
  - Verified programmatic round-trip lossless re-ingestion ($\text{Ingest}(\text{Export}(S)) == S$).
- **Tiered Stripe Subscriptions & Quota Metering**:
  - Free (5 pages/mo), Starter (50 pages/mo at \$19/mo), and Pro (500 pages/mo at \$49/mo) plans.
  - Bi-modal billing architecture supporting live Stripe Checkout/Portal as well as a zero-config local Mock Simulator.
  - Idempotent webhook handling with event deduplication for `checkout.session.completed`, `customer.subscription.updated`, and `customer.subscription.deleted`.
  - Atomic monthly page-quota tracking and over-limit gating.
- **Production-Ready Multi-Tenant Architecture**:
  - Multi-tenant data isolation with SQLite / PostgreSQL (Supabase ready).
  - JWT authentication with BCrypt password hashing.
  - Comprehensive health check endpoint (`/api/health`).

---

## Architecture

```
                      +-----------------------------+
                      |      Custom Domain / DNS    |
                      +--------------+--------------+
                                     |
               +---------------------+---------------------+
               |                                           |
               v                                           v
    +----------------------+                    +----------------------+
    |  Frontend on Vercel  |                    |  Backend (FastAPI)   |
    |  React 18 / Vite / TS|--- (/api/* rewrites)--> Render / Fly.io /  |
    |  (Static Edge CDN)   |                    |  Cloud Run Container |
    +----------------------+                    +----------+-----------+
                                                           |
                                      +--------------------+--------------------+
                                      |                    |                    |
                                      v                    v                    v
                             +-----------------+  +-----------------+  +-----------------+
                             |    Supabase     |  |     Stripe      |  |  Gemini AI /    |
                             |   PostgreSQL    |  |  Checkout & WH  |  |  Multimodal OCR |
                             +-----------------+  +-----------------+  +-----------------+
```

---

## Quickstart (Local Development)

### Prerequisites
- Python 3.12+ (managed with `uv`)
- Node.js 20+

### 1. Clone & Setup
```bash
git clone https://github.com/mgjeff22/bank-statement-parser-saas.git
cd bank-statement-parser-saas
```

### 2. Run the Full Application (Single Command)
```bash
# Starts FastAPI server serving both API and built React frontend
uv run --python 3.12 --project backend uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in your browser!

### 3. Run Automated Tests
```bash
# Run the 200 E2E tests across Tiers 1-5
uv run --python 3.12 --with pytest --with pydantic --with openpyxl --with reportlab --with pillow python tests_e2e/run_e2e.py

# Run all 123 backend pytest unit & integration tests
uv run --python 3.12 --project backend pytest backend/tests/
```

---

## Cloud Deployment Guide

See [`DEPLOYMENT.md`](DEPLOYMENT.md) for full instructions covering:
- **Supabase (PostgreSQL)**: Database setup and running migrations in [`supabase/migrations/20260928_initial_schema.sql`](supabase/migrations/20260928_initial_schema.sql).
- **Stripe**: Live keys, webhook signing secrets, and Customer Billing Portal.
- **Vercel**: Static React frontend deployment with [`vercel.json`](vercel.json) API rewrites.
- **Render / Fly.io / Docker**: 1-click containerized deployment using [`render.yaml`](render.yaml), [`fly.toml`](fly.toml), or [`Dockerfile`](Dockerfile).

---

## Environment Variables

Copy `.env.production.example` to `.env` and fill in your values:

```bash
PROJECT_NAME="AI Bank Statement Parser"
API_V1_STR="/api"
SECRET_KEY="your-random-64-character-jwt-signing-secret"
DATABASE_URL="postgresql://postgres.[REF]:[PASS]@aws-0-[REGION].pooler.supabase.com:6543/postgres?pgbouncer=true"
BILLING_MODE="live" # or 'mock' for local zero-config testing
STRIPE_SECRET_KEY="sk_live_..."
STRIPE_PUBLISHABLE_KEY="pk_live_..."
STRIPE_WEBHOOK_SECRET="whsec_..."
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
