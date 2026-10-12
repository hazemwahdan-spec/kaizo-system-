-- Canonical Phase 4 identity/consent contract used by phase4_identity_store.py.
-- Disposable/CI validation first. This is additive and must not be auto-applied to production.
BEGIN;

CREATE TABLE IF NOT EXISTS kaizo_tenants (
    tenant_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kaizo_tenant_memberships (
    membership_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    academy_id TEXT NOT NULL REFERENCES kaizo_tenants(tenant_id),
    role TEXT NOT NULL CHECK (role IN ('academy', 'coach', 'athlete', 'parent')),
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'suspended')),
    version INTEGER NOT NULL CHECK (version > 0),
    resource_owner_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (actor_id, academy_id, role, version)
);
CREATE INDEX IF NOT EXISTS idx_kaizo_membership_lookup
    ON kaizo_tenant_memberships (actor_id, academy_id, role, version DESC);

CREATE TABLE IF NOT EXISTS kaizo_resource_tenant_bindings (
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    tenant_id TEXT NOT NULL REFERENCES kaizo_tenants(tenant_id),
    bound_by_actor_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (resource_type, resource_id)
);
CREATE INDEX IF NOT EXISTS idx_kaizo_resource_tenant
    ON kaizo_resource_tenant_bindings (tenant_id, resource_type);

CREATE TABLE IF NOT EXISTS kaizo_guardian_relationships (
    relationship_id TEXT PRIMARY KEY,
    child_id TEXT NOT NULL,
    guardian_actor_id TEXT NOT NULL,
    academy_id TEXT NOT NULL REFERENCES kaizo_tenants(tenant_id),
    verification_status TEXT NOT NULL
        CHECK (verification_status IN ('pending', 'verified', 'rejected', 'revoked')),
    version INTEGER NOT NULL CHECK (version > 0),
    verified_by TEXT,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (
        (verification_status = 'verified' AND verified_by IS NOT NULL AND verified_at IS NOT NULL)
        OR verification_status <> 'verified'
    ),
    UNIQUE (child_id, guardian_actor_id, academy_id, version)
);
CREATE INDEX IF NOT EXISTS idx_kaizo_guardian_lookup
    ON kaizo_guardian_relationships
       (child_id, guardian_actor_id, academy_id, version DESC);

-- P14 consent history uses the exact table/column contract consumed by the adapter.
CREATE TABLE IF NOT EXISTS kaizo_child_consents (
    consent_id TEXT PRIMARY KEY,
    child_id TEXT NOT NULL,
    guardian_actor_id TEXT NOT NULL,
    academy_id TEXT NOT NULL REFERENCES kaizo_tenants(tenant_id),
    resource TEXT NOT NULL,
    action TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'active', 'revoked', 'expired')),
    expires_at TIMESTAMPTZ NOT NULL,
    recorded_by_actor_id TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (child_id, guardian_actor_id, academy_id, resource, action, version)
);
CREATE INDEX IF NOT EXISTS idx_kaizo_consent_scope
    ON kaizo_child_consents
       (child_id, guardian_actor_id, academy_id, resource, action, version DESC);

CREATE TABLE IF NOT EXISTS kaizo_authorization_audit (
    event_id TEXT PRIMARY KEY,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    correlation_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    actor_role TEXT,
    academy_id TEXT REFERENCES kaizo_tenants(tenant_id),
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    action TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('allow', 'deny')),
    reason_code TEXT NOT NULL,
    consent_id TEXT,
    policy_version TEXT NOT NULL,
    request_route TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_kaizo_auth_audit_correlation
    ON kaizo_authorization_audit (correlation_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_kaizo_auth_audit_actor
    ON kaizo_authorization_audit (actor_id, occurred_at);

COMMIT;
