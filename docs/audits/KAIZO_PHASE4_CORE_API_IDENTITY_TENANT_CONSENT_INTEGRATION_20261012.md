# KAIZO Phase 4 — Core API Identity, Tenant and P14 Consent Integration

**Date:** 2026-10-12  
**Status:** Integration candidate — CI validation pending  
**Requirement:** P4-REQ-011 remains OPEN until all checks and independent retest pass.

## Route enforcement added

The backend/main.py Core API now attaches the Phase 4 guard to athlete reads/updates and athlete-bound routes:
- create/get assessment and attach/list assessment evidence
- create/list problem statements, diagnosis, cause-context, decision candidates/comparisons/rationales/reviews/records
- create/get training plans, sessions and dosage
- KPI capture, evidence creation/retrieval/listing, state snapshots, Digital Twin sync/retrieval, rules/safety evaluation, and decision loop/adapt
- athlete creation is gated by verified OIDC and active database membership; new athlete IDs receive a server-side athlete tenant binding from the verified principal's tenant
- athlete-filtered collection routes require an athlete/subject scope; unscoped collections are denied rather than returning cross-academy data.

## Authorization path

1. Require KAIZO_PHASE4_IDENTITY_ENFORCEMENT=oidc; otherwise return 503 (fail closed).
2. Verify the bearer JWT against configured OIDC issuer, audience and JWKS; invalid/missing token returns 401.
3. Require a coach/academy role and active kaizo_tenant_memberships row for the verified subject and tenant.
4. Resolve the athlete from the persisted child-resource ownership chain; body actor/tenant fields do not establish identity or ownership.
5. Require a matching kaizo_resource_tenant_bindings row for the athlete and the principal's tenant.
6. For known minors and unknown-age athletes, require a verified guardian relationship and latest active, unexpired P14 consent for the exact route action and resource scope.
7. Record allow/deny decisions in kaizo_p14_audit_events within the same database transaction. Failure to persist the audit fails closed.

## Tests added

- Deterministic HTTP contract tests through the actual FastAPI route for cross-tenant, missing-consent, revoked/superseded-consent, and unverified-identity denial.
- PostgreSQL-backed route tests run against the disposable PostgreSQL service. They create tenant, membership, resource binding and guardian/consent records, then assert HTTP 403 and a durable deny audit for cross-tenant access, absent consent, and a newer revoked consent superseding an older active row.
- Migration remains additive and is applied only to the CI disposable database in this workflow.

## Rollout limitations / gates

- No production database migration, tenant ownership backfill, Auth0 setting change, or production write was performed.
- Existing athlete records remain unbound until a separately reviewed, evidence-backed ownership backfill is executed. They are denied by default.
- The production OIDC environment gate and issuer/audience/JWKS values must be configured and verified before the guarded routes can be used. This PR does not alter production variables.
- Guardian identity verification and consent enrollment must be sourced from a trusted process; request-body guardian_id or actor fields are not accepted as proof.
- The scope is athlete-bound routes in backend/main.py; separate routers (feature runtime, training workflow, knowledge, evidence-safety, state-cycle, reporting, competition and academy operations) still require route inventory/integration before claiming complete Phase 4 coverage. Global audit-log tenant filtering also remains a separate gate.
- Do not close P4-REQ-011 or Phase 4 EXIT until this PR's checks pass, ownership backfill is reviewed, remaining protected routes are covered, controlled verification succeeds, and an independent retest passes.
- Coach Final Authority remains mandatory; no autonomous execution is authorized.
