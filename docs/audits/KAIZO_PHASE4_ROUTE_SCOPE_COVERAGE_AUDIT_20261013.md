# KAIZO Phase 4 — Route/Resource Scope Coverage Audit

Date: 2026-10-13  
PR: [#128 — Phase 4 Core resource authorization](https://github.com/hazemwahdan-spec/kaizo-system-/pull/128)  
Validated code head: `458eb1641adb8c10e9f54cefb702f4759e4b13df`  
Disposition: **BLOCKED — CI is green, production security proof remains incomplete**

## Evidence examined

- Actual registered FastAPI route inventory: `backend/test_phase4_actual_app_route_inventory.py`.
- Core authorization and identity/consent adapters: `backend/phase4_core_resource_authorization.py`, `backend/phase4_identity_store.py`.
- Core handlers and router mounts: `backend/main.py`.
- Mounted routers: training workflow, knowledge runtime, audit trace runtime, evidence safety runtime, state cycle, reporting runtime, competition runtime, academy operations, and generated feature runtime.
- HTTP acceptance tests: `backend/test_phase4_core_resource_authorization.py`.
- Canonical identity/consent migration and integration test: `backend/migrations/20261012_phase4_identity_consent_canonical.sql`, `backend/test_phase4_canonical_identity_consent_integration.py`.

## Current CI evidence

The current candidate head `458eb1641adb8c10e9f54cefb702f4759e4b13df` has **20/20 retrieved workflow runs completed successfully**, including:

- [Persistence Adapter Validation](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38347280138) — compilation, existing feature acceptance suite, canonical identity/consent integration, and actual Core resource authorization HTTP tests.
- [Phase 4 Actual Core Route Inventory](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38347280190) — registered non-product routes have the identity gate; mounted/generated routes have the fail-closed scope guard.
- [Phase 4 Live Runtime Smoke](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38347280179) — bounded deployed health/OpenAPI smoke only; it does **not** prove that this branch is deployed or that production OIDC and every protected route have been independently verified.
- [Phase 7 Runtime Adapter](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38347280148) — internal direct Core invocation updated to pass an explicit principal.
- [Commercial Security Regression](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38347280185).

## Route coverage matrix

| Route/resource family | Candidate guard/evidence | Remaining proof |
|---|---|---|
| Athlete create/read/update | Atomic athlete tenant binding on create; tenant + age/consent checks on read/update | Production OIDC identity and live allow/deny retest |
| Assessment create/read | Parent athlete and assessment tenant checks; atomic persistence/binding/audit; consent checks | Production OIDC identity and live allow/deny retest |
| Problem statements and scoped lists | Parent-chain tenant resolution; read/write and consent guards; unscoped list requests fail closed | Exhaustive per-route cross-tenant and no-read/no-write matrix |
| Diagnosis, candidates, rationale, comparisons, coach review, decision records | Parent-chain resolver; tenant and consent guards; evidence ownership checks before evidence reads | Full per-route wrong-parent/forged-link matrix |
| Training plans, sessions, dosage, cause context, problem-library selections | Tenant and consent guards tied to athlete/decision/problem parent chains | Full route-by-route regression and cross-parent mismatch matrix |
| KPI captures and state snapshots | Athlete/assessment/capture tenant checks and child consent; unscoped list requests fail closed | KPI definition remains a shared/global catalog and needs an explicit governance/role policy |
| Evidence create/read/list | Scoped subject types resolve to a persisted athlete parent; unsupported production subject types deny; feature/rule fixtures are exempt only for explicit test principals | Explicit policy for every production evidence subject type and per-type negative tests |
| Audit log endpoint | Production reads only durable authorization events filtered by authenticated academy; global legacy audit log is exposed only to explicit test principals | Verify production data retention/operations and audit completeness for all runtimes |
| Digital Twin, rules, safety, decision loop/adapt | Tenant/consent checks added; case IDs must resolve to one same-academy persisted resource; unknown cases deny | Verify all case/resource mappings and ensure every state transition is linked to an authoritative parent |
| Mounted and generated feature routers | Shared `require_router_resource_scope` gate attached to every mounted router; it fails closed if no supported persisted resource reference can be resolved | The generic gate is a safety backstop, not a substitute for route-specific role, parent-link, consent, and audit policies. Some unsupported/global routes intentionally remain unavailable until classified |
| Shared problem library / KPI catalog / knowledge ingest | Identity gate present | Explicit classification of global vs academy-owned data, publisher role policy, and tenant-safe mutation/read contract |
| Health and governed commercial-product endpoints | Separate policy boundary | Not covered by this Core Phase 4 resource matrix |

## Important implementation boundary

The candidate now does more than attach an identity dependency: it resolves supported child-resource ownership through persisted parent chains, checks child consent on covered Core handlers, denies unscoped list operations, adds a default-deny scope dependency to mounted/generated routers, and scopes production audit-log reads to the authenticated academy.

However, **green CI is not proof of full production activation**. Some mounted/global endpoints are intentionally denied when the generic guard cannot establish ownership. The route-specific policy matrix, supported subject/resource inventory, and live production allow/deny cases still need independent verification.

## Required closure work

1. Complete the machine-readable manifest for every registered and deployed route: method/path, router, resource type, parent chain, identity/role gate, tenant resolver, consent applicability, audit event, and test evidence.
2. Replace the generic backstop with explicit route-family policies for every mounted/generated route; verify no route silently relies on client-supplied tenant, actor, guardian, or parent identifiers.
3. Add/execute cross-tenant no-read/no-write, wrong-parent, missing/revoked/expired-consent, and durable-audit tests for every sensitive resource family—not just representative routes.
4. Define and execute the trusted operational process for age classification and guardian relationship verification. Persistence primitives alone do not prove who may attest those facts.
5. Independently verify production OIDC issuer, audience, JWKS, token/claim mapping, canonical migrations, and live allow/deny behavior against the exact deployed commit.
6. Capture independent retest, regression, rollback, and production health evidence after a separately authorized deployment.

## Governance decision

- `P4-REQ-011 = OPEN / NOT PROVEN`
- `Phase 4 EXIT = BLOCKED`
- PR #128 remains a draft and must not be merged as a phase-closure action until all closure gates above are met.

Evidence Before Claim. This audit records the current candidate boundary; it does not assert that unverified routes are secure or that the candidate is deployed.
