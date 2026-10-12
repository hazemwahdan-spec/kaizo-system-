-- KAIZO Phase 4 tenant/resource ownership + P14 durable-consent schema.
-- Additive only: does not assign existing records to a tenant, grant consent,
-- alter routes, or enable production enforcement. Backfill requires a verified
-- ownership source and a separately reviewed migration plan.

BEGIN;

CREATE TABLE IF NOT EXISTS kaizo_tenants (
    tenant_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'ARCHIVED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kaizo_tenant_memberships (
    membership_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL REFERENCES kaizo_tenants(tenant_id),
    subject_id TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'REVOKED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (tenant_id, subject_id, role)
);
CREATE INDEX IF NOT EXISTS idx_kaizo_membership_subject
    ON kaizo_tenant_memberships(subject_id, status);
CREATE INDEX IF NOT EXISTS idx_kaizo_membership_tenant_role
    ON kaizo_tenant_memberships(tenant_id, role, status);

-- Resource ownership is explicit and server-side. No request-body tenant label
-- may create or override a binding. resource_id refers to the canonical ID in
-- the owning domain table; cross-domain FK constraints are enforced by service
-- logic because resource types span multiple tables.
CREATE TABLE IF NOT EXISTS kaizo_resource_tenant_bindings (
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES kaizo_tenants(tenant_id),
    bound_by_subject TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resource_type, resource_id)
);
CREATE INDEX IF NOT EXISTS idx_kaizo_resource_tenant
    ON kaizo_resource_tenant_bindings(tenant_id, resource_type);

CREATE TABLE IF NOT EXISTS kaizo_guardian_relationships (
    relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_resource_id TEXT NOT NULL,
    guardian_subject_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES kaizo_tenants(tenant_id),
    relationship_type TEXT NOT NULL,
    verification_status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (verification_status IN ('PENDING', 'VERIFIED', 'REJECTED', 'REVOKED')),
    verified_by_subject TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (verification_status = 'VERIFIED'
            AND verified_by_subject IS NOT NULL AND verified_at IS NOT NULL)
        OR verification_status <> 'VERIFIED'
    )
);
CREATE INDEX IF NOT EXISTS idx_kaizo_guardian_lookup
    ON kaizo_guardian_relationships(child_resource_id, tenant_id, verification_status);
CREATE INDEX IF NOT EXISTS idx_kaizo_guardian_subject
    ON kaizo_guardian_relationships(guardian_subject_id, tenant_id, verification_status);

-- Consent history is append-oriented. A new row supersedes neither historical
-- records nor authorization checks; callers must select the latest applicable
-- scoped record and deny absent, pending, revoked, expired, or mismatched consent.
CREATE TABLE IF NOT EXISTS kaizo_p14_consents (
    consent_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_resource_id TEXT NOT NULL,
    guardian_subject_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES kaizo_tenants(tenant_id),
    resource_type TEXT NOT NULL,
    action TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'active', 'revoked', 'expired')),
    expires_at TIMESTAMPTZ,
    recorded_by_subject TEXT NOT NULL,
    source_reference TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS idx_kaizo_p14_consent_scope
    ON kaizo_p14_consents(
        child_resource_id, guardian_subject_id, tenant_id,
        resource_type, action, created_at DESC
    );

CREATE TABLE IF NOT EXISTS kaizo_p14_audit_events (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actor_subject_id TEXT,
    event_type TEXT NOT NULL,
    child_resource_id TEXT,
    guardian_subject_id TEXT,
    tenant_id TEXT,
    resource_type TEXT,
    action TEXT,
    allowed BOOLEAN,
    reason_code TEXT NOT NULL,
    trace_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_kaizo_p14_audit_scope_time
    ON kaizo_p14_audit_events(tenant_id, child_resource_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_kaizo_p14_audit_trace
    ON kaizo_p14_audit_events(trace_id) WHERE trace_id IS NOT NULL;

COMMIT;
