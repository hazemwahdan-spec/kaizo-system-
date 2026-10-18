# KAIZO Global Evidence Publisher Policy — 2026-10-18

**Status:** Implemented in code; production activation remains gated.  
**Scope:** Legacy `/api/v1/evidence` global/shared evidence API only. This does not close Phase 4.

## Policy decision

1. The endpoint is disabled by default. Missing or false `KAIZO_EVIDENCE_PUBLISHER_ENABLED` returns HTTP 503.
2. When explicitly enabled, every list, detail, and write request requires a verified OIDC JWT resolved by the existing KAIZO identity boundary.
3. The signed principal must carry `role=publisher` (or the configured `kaizo_role=publisher` claim) and the exact global tenant claim configured by `KAIZO_EVIDENCE_GLOBAL_TENANT_ID` (default `global`).
4. The client-supplied `verified_by` value is never treated as identity. Stored verifier identity and audit actor are derived from the verified JWT subject.
5. This endpoint accepts only global `rule` and `catalog` evidence. Academy-owned athlete, assessment, and problem evidence is denied here and must use a separate route that proves authenticated tenant membership, parent-resource ownership, applicable guardian consent, and durable authorization audit.
6. Global evidence writes and their durable audit event are committed in one PostgreSQL transaction. Memory-mode persistence cannot authorize this endpoint.
7. Global list/detail reads filter to global subject types only. Tenant-owned records are not disclosed through the global API.

## Production activation gates

Do not enable the feature flag until all of the following are independently verified:

- Auth0 issues signed KAIZO custom claims `kaizo_role=publisher` and `tenant_id=global` only to approved publisher identities.
- The production service has the correct Auth0 issuer, audience, and JWKS trust configuration.
- `KAIZO_EVIDENCE_PUBLISHER_ENABLED=true` and `KAIZO_EVIDENCE_GLOBAL_TENANT_ID=global` are configured in the intended production environment.
- Live tests with a real approved publisher token prove global rule/catalog allow, client `verified_by` spoofing is ignored, non-publisher and wrong-tenant denial, anonymous denial, tenant-owned evidence denial, and durable audit persistence.
- The exact deployed commit is recorded and independently checked.

Until these gates pass, leave the feature flag unset/false. The public evidence route must remain unavailable rather than falling back to caller-asserted identity.

## Required verification boundary

A green CI run proves code-level behavior only. It does not prove Auth0 claim configuration or production activation. Phase 4 remains open until route-wide identity/RBAC, tenant isolation, guardian consent where applicable, durable audit, and live deployment evidence are independently verified.
