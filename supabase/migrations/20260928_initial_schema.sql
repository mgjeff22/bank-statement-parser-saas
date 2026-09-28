-- Supabase / PostgreSQL Initial Schema Migration for AI Bank Statement Parser Micro-SaaS
-- Run this in the Supabase SQL Editor or apply via Supabase CLI

CREATE TABLE IF NOT EXISTS tenants (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(32) NOT NULL DEFAULT 'owner',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_tenant_id ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS subscriptions (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) UNIQUE NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    stripe_customer_id VARCHAR(100),
    stripe_subscription_id VARCHAR(100) UNIQUE,
    tier VARCHAR(32) NOT NULL DEFAULT 'free',
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    monthly_page_limit INTEGER NOT NULL DEFAULT 5,
    current_period_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_tenant_id ON subscriptions(tenant_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer_id ON subscriptions(stripe_customer_id);

CREATE TABLE IF NOT EXISTS quota_usages (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    year_month VARCHAR(7) NOT NULL,
    pages_used INTEGER NOT NULL DEFAULT 0,
    monthly_limit INTEGER NOT NULL DEFAULT 5,
    last_reset_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_year_month UNIQUE (tenant_id, year_month)
);

CREATE INDEX IF NOT EXISTS idx_quota_usages_tenant_id ON quota_usages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_quota_usages_year_month ON quota_usages(year_month);

CREATE TABLE IF NOT EXISTS statements (
    id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(512) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'queued',
    page_count INTEGER NOT NULL DEFAULT 1,
    bank_name VARCHAR(255),
    statement_period_start VARCHAR(32),
    statement_period_end VARCHAR(32),
    starting_balance VARCHAR(32),
    ending_balance VARCHAR(32),
    total_credits VARCHAR(32),
    total_debits VARCHAR(32),
    net_cashflow VARCHAR(32),
    discrepancy VARCHAR(32),
    is_reconciled BOOLEAN,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_statements_tenant_id ON statements(tenant_id);
CREATE INDEX IF NOT EXISTS idx_statements_user_id ON statements(user_id);

CREATE TABLE IF NOT EXISTS processed_stripe_events (
    id VARCHAR(64) PRIMARY KEY,
    event_id VARCHAR(100) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    payload_hash VARCHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'processed'
);

CREATE INDEX IF NOT EXISTS idx_processed_stripe_events_event_id ON processed_stripe_events(event_id);
