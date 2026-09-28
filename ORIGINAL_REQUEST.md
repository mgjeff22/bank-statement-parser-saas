# Original User Request

## 2026-09-28T18:44:15Z

Build a production-grade, full-stack AI Bank Statement Parser Micro-SaaS application with tiered subscription billing, universal multimodal statement extraction (PDF and scanned images), balance reconciliation, interactive transaction editing, and multi-format data export.

Working directory: C:\Users\Josh\teamwork_projects\bank_statement_parser
Integrity mode: development

## Requirements

### R1. Multimodal Bank Statement Parsing & Reconciliation Engine
Process bank statements uploaded as PDFs (digital and scanned) and images (PNG, JPEG, WebP). Extract structured transaction records containing date, payee/description, transaction type (debit/credit), amount, category, and running balance. Perform automatic balance reconciliation: verify that starting balance plus credits minus debits equals the reported ending balance, flagging discrepancies.

### R2. Interactive Transaction Workspace & Exporter
Provide an interactive user interface to inspect uploaded statements alongside their extracted data. Users can review, filter, edit, add, or delete transactions, resolve parsing anomalies, and verify flagged reconciliation mismatches. Implement one-click data export to clean CSV, formatted Excel (.xlsx) with proper column datatypes, and structured JSON.

### R3. Subscription Management, Stripe Billing & Quota Metering
Implement tiered subscription access (e.g. Free/Starter/Pro tiers) with monthly page-processing limits. Integrate Stripe Checkout for monthly and annual billing, Stripe Customer Portal for managing subscriptions/payment methods, and secure Stripe webhook listeners for real-time subscription lifecycle events (creation, invoice payment, upgrades, and cancellations). Include a full-featured mock/demo billing mode allowing immediate local testing without live API keys.

### R4. Multi-Tenant SaaS Dashboard & Authentication
Provide secure user authentication and account management. The user dashboard must display processing usage meters against subscription quotas, statement upload history with status indicators (processing, completed, error), and secure file management.

## Acceptance Criteria

### Automated Parsing & Reconciliation Verification
- [ ] Automated end-to-end tests parse synthetic/sample bank statement files (PDF and image) and achieve 100% extraction of transaction records against reference ground truth datasets.
- [ ] Balance reconciliation logic computes net cashflow and mathematically verifies the ending balance, correctly flagging deliberate mismatches in test cases.

### Subscription & Quota Enforcement Verification
- [ ] Automated test suite verifies subscription tier gating: users on restricted plans are blocked when exceeding their allotted monthly quota.
- [ ] Stripe webhook handler tests verify idempotent processing of `checkout.session.completed`, `customer.subscription.updated`, and `customer.subscription.deleted`.
- [ ] Mock billing toggle functions seamlessly, allowing automated verification of subscription upgrades and cancellations end-to-end.

### Export Integrity Verification
- [ ] Automated exporter tests verify generated CSV and XLSX files contain all transaction rows with valid headers, proper number/currency formatting, and exact reconciliation totals matching the UI dataset.
- [ ] Generated files can be downloaded and parsed programmatically without schema corruption.

### End-to-End Application Launch & Health
- [ ] Application starts cleanly with automated build/lint checks passing and provides health check endpoints confirming UI, database/storage, and parsing pipeline readiness.
