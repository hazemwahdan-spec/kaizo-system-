# KAIZO Phase 4 — Route/Resource Scope Coverage Audit

Date: 2026-10-13  
PR: #128 — `feat/phase4-core-resource-authorization`  
Reviewed head before this audit: `12a27cb88c12e3c2a085333a6b9a3953768d678d`  
Disposition: **BLOCKED — inventory is not authorization proof**

## Evidence examined

- Actual registered FastAPI route inventory test: `backend/test_phase4_actual_app_route_inventory.py`.
- Core route authorization implementation: `backend/phase4_core_resource_authorization.py`.
- Actual app handlers and router mounts: `backend/main.py`.
- Mounted routers: training workflow, knowledge runtime, audit trace runtime, evidence safety runtime, state cycle, reporting runtime, competition runtime, academy operations, and generated feature runtime.
- HTTP acceptance tests: `backend/test_phase4_core_resource_authorization.py`.
- Canonical identity/consent migration and adapter: `backend/migrations/20261012_phase4_identity_consent_canonical.sql`, `backend/phase4_identity_store.py`.

## What is evidenced

1. The actual-app inventory test imports `backend.main:app` and walks registered `APIRoute` dependency trees, including mounted and generated routes.
2. Mounted routers are registered with `Depends(require_core_actor)`; this proves an identity/membership gate is attached, not that resource ownership is checked.
3. The current resource authorization implementation provides database-backed tenant binding, membership, verified age classification, scoped guardian-consent lookup, and durable allow/deny audit primitives.
4. The route-level HTTP tests cover fail-closed identity, membership denial, cross-tenant denial before athlete/assessment reads, missing age classification, missing minor consent, and audit-store failure in the tested scenarios.
5. The latest retrieved workflow set for head `12a27cb88c12e3c2a085333a6b9a3953768d678d` reports success for the Phase 4 Actual Core Route Inventory, Phase 4 Live Runtime Smoke, and Persistence Adapter Validation. This is CI evidence only; it is not independent production OIDC verification.

## Route coverage matrix

| Route/resource family | Identity gate evidence | Tenant/resource ownership evidence | Consent evidence | Disposition |
|---|---|---|---|---|
| Athlete create/read/update | Present in actual Core handlers | Binding/check primitives and HTTP negative tests exist | Read/write checks call age/consent guard | Partial; production identity not independently verified |
| Assessment create/read | Present in actual Core handlers | Athlete and assessment binding checks exist; negative HTTP tests cover cross-tenant cases | Exact resource/action guard called | Partial; production identity not independently verified |
| Assessment evidence attach/list | Identity dependency declared | No equivalent end-to-end tenant-chain proof recorded in this audit | No route-level consent proof recorded | Open |
| Problem statements, diagnosis, cause context | Identity dependency declared | Must resolve problem -> athlete and assessment -> same athlete; complete negative HTTP matrix not evidenced | Must inherit child consent scope | Open |
| Decision candidates, rationale, comparisons, coach review, decision records | Identity dependency declared | Must resolve decision -> diagnosis -> problem -> athlete and enforce academy/coach assignment | Must inherit applicable consent | Open |
| Training plans, sessions, dosage | Identity dependency declared | Must resolve plan/session/dosage ownership through persisted parent chain | Must enforce exact child/resource/action consent | Open |
| KPI definitions/captures, evidence, state snapshots, digital twin, decision loop/adapt | Identity dependency declared | Per-resource tenant binding and no-read/no-write tests not evidenced for every route | Consent applicability not evidenced route-by-route | Open |
| Rules, safety evaluation, knowledge ingest, audit log listing | Identity dependency declared | Tenant-scoped read/write and privileged audit-read policy need explicit tests | Consent applicability must be classified explicitly | Open |
| Mounted training/knowledge/audit/evidence-safety/state/reporting/competition/academy-ops routers | Router-level identity dependency attached | Router-by-router resource ownership/academy isolation matrix not complete | Consent and guardian relationship matrix not complete | Open |
| Generated feature create/get/list routes | Router-level identity dependency attached | Every generated route and underlying feature record needs scope policy; inventory alone is insufficient | Consent applicability must be explicit per feature/resource | Open |
| Health and governed commercial-product endpoints | Explicitly excluded from the non-product identity inventory rule | Separate public/product governance applies | Not covered by this Phase 4 resource matrix | Separate policy |

## Required closure work

1. Build an exhaustive machine-readable route manifest from the deployed OpenAPI and the actual registered app routes at the same commit. Include method, path, router, resource type, parent chain, identity gate, role policy, tenant resolver, consent policy, audit event, and test evidence.
2. For every protected resource family, bind ownership atomically with creation and derive nested ownership from persisted parent records. Do not trust tenant/actor/guardian fields supplied by the client.
3. Add real HTTP acceptance tests per route family for unauthenticated/invalid identity, inactive membership, cross-academy access, no-read/no-write denial, wrong parent linkage, missing/revoked/expired consent, and durable audit. Unsupported or unbound resources must fail closed.
4. Define and execute the trusted operational process for verifying age classifications and guardian relationships. The persistence primitives do not themselves prove who is authorized to attest those facts.
5. Independently verify production OIDC issuer, audience, JWKS, claim mapping, canonical migrations, and live allow/deny behavior. Keep production secrets/configuration untouched unless separately authorized.
6. Run independent retest plus regression/rollback evidence against the exact candidate commit.

## Governance decision

- `P4-REQ-011 = OPEN / NOT PROVEN`
- `Phase 4 EXIT = BLOCKED`
- PR #128 remains a draft and must not be merged as a phase-closure action until the route/resource matrix and independent production evidence satisfy the exit gates.

Evidence Before Claim. This document records the audit boundary; it does not claim that untested routes are secure.
