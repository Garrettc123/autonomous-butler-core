-- ============================================================
-- Autonomous Butler Core – Billing Schema
-- ============================================================

-- Tenants table: one row per paying customer / subscription
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tier                 TEXT NOT NULL CHECK (tier IN ('starter', 'growth', 'enterprise')),
    status               TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled', 'past_due')),
    stripe_customer_id   TEXT NOT NULL UNIQUE,
    stripe_subscription_id TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenants_stripe_customer ON tenants (stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_tenants_status ON tenants (status);

-- Tenant events table: append-only audit ledger for all billing events
CREATE TABLE IF NOT EXISTS tenant_events (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stripe_customer_id   TEXT NOT NULL,
    event_type           TEXT NOT NULL,
    payload              JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_events_customer ON tenant_events (stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_tenant_events_type ON tenant_events (event_type);
CREATE INDEX IF NOT EXISTS idx_tenant_events_created ON tenant_events (created_at DESC);

-- Row-level security: scope all tenant data to the owning tenant
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_events ENABLE ROW LEVEL SECURITY;

-- Service-role bypass (used by the backend only)
CREATE POLICY tenants_service_all ON tenants
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY tenant_events_service_all ON tenant_events
    TO service_role
    USING (true)
    WITH CHECK (true);
