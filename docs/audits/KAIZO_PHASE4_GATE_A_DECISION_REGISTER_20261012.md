# KAIZO Phase 4 — Gate A Decision Register

Date: 2026-10-12  
Related: P4-REQ-011, PR #122, P13 Identity/RBAC, P14 Minor Consent  
Status: OPEN — decisions below are not approved by this artifact  
Evidence rule: Evidence Before Claim

## Verified evidence at this checkpoint

- PR #122 head at this register update: `c5ea798fab5bced7adbfde0324b63d306afbb2e6` (open, draft, mergeable; not merged).
- Latest PR-triggered CI on `c5ea798fab5bced7adbfde0324b63d306afbb2e6` completed successfully for Persistence Adapter Validation run 38201139493, Phase 4 Live Runtime Smoke run 38201139495, Phase 7 Identity RBAC Boundary run 38201139525, and the listed Phase 7/product/security integration workflows.
- The implementation commit `f6ba0a907e6fcbf94b5621b85788dfddfcf5884d` also passed Persistence Adapter Validation run 38201027285, including the new ephemeral-PostgreSQL identity/consent-store tests.
- Smoke is limited to OpenAPI/health checks; identity and persistence tests are contract/store-level CI evidence.
- These checks do not prove actual Core route enforcement, trusted membership provisioning, real guardian verification, production consent/audit persistence, or live tenant/resource isolation.

## Gate A decisions required before schema/repository implementation

| Decision | Required resolution | Safe state until resolved |
|---|---|---|
| Canonical academy/tenant identifier | Confirm canonical field, source of truth, and whether it maps to the current OIDC `tenant_id` claim | Reject tenant-sensitive authorization that cannot derive scope server-side |
| Membership provisioning authority | Identify trusted administrative provisioning path and who may create/revoke academy memberships | Never infer membership from request payload or role claim alone |
| OIDC claim contract | Approve issuer, audience, JWKS source, subject semantics, role mapping, and tenant claim mapping for the chosen production target | Keep Phase 4 identity enforcement disabled |
| Guardian verification | Specify trusted evidence/source, verifier authority, verification/revocation process, and child/guardian/academy identity linkage | Parent role alone never grants child access |
| Consent lifecycle | Approve who may grant/revoke, required scope, effective/expiry behavior, non-expiring-consent policy, and state transitions | Missing, pending, revoked, expired, or scope-mismatched consent denies |
| Resource/action vocabulary | Approve stable resource types and action names used by routes and consent records | Do not create guessed policy values or claim route coverage |
| Audit and privacy | Approve correlation ID, reason codes, retention/deletion, minimization, and transaction/failure behavior | No tokens or unnecessary child-sensitive payloads in audit; fail closed if required audit cannot persist |
| Canonical production target | Confirm which deployed service is authoritative (FastAPI Cloud vs Railway) and which database is attached to it | No production schema, environment, or live-data changes |
| Change authorization | Explicitly authorize the eventual production configuration/schema/write window and test scope | No production writes or identity-provider activation |

## Required implementation gates

1. **Gate A — contract approval:** resolve the decisions above using authoritative deployment/provider details and the approved P13/P14 policy.
2. **Gate B — persistence:** versioned migrations and repository methods; constraints, lifecycle, concurrency, and durable-audit tests against ephemeral PostgreSQL only.
3. **Gate C — route enforcement:** use the shared OIDC principal; derive resource ownership from persisted records; cover actual Core and feature routes with no-read/no-write leakage tests.
4. **Gate D — controlled runtime:** only after separate explicit authorization; verify actual provider configuration and target, begin with read-only negative checks.
5. **Gate E — independent retest:** record exact commit and workflow evidence; close P4-REQ-011 only when all requirements are proven.

## Current disposition

P4-REQ-011 remains **OPEN / NOT PROVEN**. PR #122 remains a draft implementation candidate. This register does not approve the contract, apply a schema, change runtime settings, or authorize production writes. Coach Final Authority remains intact and training execution remains unauthorized by default.


## Implementation progress after this register was created

A **non-production candidate implementation** has now been added to this draft PR for review:
- `backend/migrations/0001_phase4_identity_consent.sql`: versioned membership, guardian relationship, child consent, and authorization audit tables.
- `backend/phase4_identity_store.py`: PostgreSQL-only append/look-up primitives. Memory mode raises a configuration error; latest-version membership/relationship/consent is used; consent requires exact child/guardian/academy/resource/action scope and a non-expired active record.
- `backend/test_phase4_identity_store.py`: ephemeral PostgreSQL lifecycle tests for membership revocation, guardian relationship revocation, consent scope/revocation/expiry, and deny-audit roundtrip.
- `.github/workflows/persistence-adapter-validation.yml`: invokes the new acceptance test in CI.

**Important limitation:** this candidate code does not establish the trusted origin of membership provisioning or guardian verification, is not wired to Core API routes, and has not been applied to any production database. The test fixture's verification actor is test-only. Gate A decisions remain OPEN; Gate B has passing isolated CI evidence but remains subject to contract review and integration acceptance. Do not merge or enable production enforcement based solely on this implementation.


## CI result — 2026-10-12

The candidate persistence implementation at commit `f6ba0a907e6fcbf94b5621b85788dfddfcf5884d` passed the complete Persistence Adapter Validation workflow, including the new **Phase 4 durable identity and consent store acceptance tests**:
- [Persistence Adapter Validation run 38201027285](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201027285) — **SUCCESS**.
- The new test applies the migration only to the workflow's ephemeral PostgreSQL service and covers membership revocation, guardian relationship revocation, exact-scope consent, consent revocation/expiry, and durable deny-audit roundtrip.
- Related identity-boundary tests passed: [run 38201027202](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201027202).
- Limited live smoke passed: [run 38201027300](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201027300).

This proves the candidate schema/store behavior in CI only. It does **not** prove trusted membership provisioning, real guardian verification, route-level enforcement in `backend.main:app`, production persistence, or live tenant/resource isolation. Therefore Gate B has test evidence for its isolated primitives but remains subject to contract review; Gate A and P4-REQ-011 remain OPEN.


## Gate evidence refresh — latest checkpoint

- PR #122 latest head `c5ea798fab5bced7adbfde0324b63d306afbb2e6`: all returned PR-triggered workflow runs completed with `success`, including Persistence Adapter Validation `38201139493`, Phase 4 Live Runtime Smoke `38201139495`, and Phase 7 Identity RBAC Boundary `38201139525`.
- Direct run links: [Persistence Adapter Validation](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201139493), [Phase 4 Live Runtime Smoke](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201139495), [Phase 7 Identity RBAC Boundary](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201139525).
- PR #123 is also open as a separate draft schema candidate (`feat/phase4-tenant-consent-schema`, head `fb13a3d3212ef6dc940445489e7e26182d241a47`). It overlaps Phase 4 data-model scope with PR #122. Neither draft is merged; they must not be independently merged or applied until the canonical migration/repository path is reconciled, to avoid duplicate/conflicting schemas.
- User's instruction to satisfy gates is treated as authorization to continue evidence-based non-production work, not as approval of unspecified identity, guardian, retention, target-environment, or production-change decisions.
- **Gate disposition remains:** CI evidence for isolated primitives = PASS; Gate A contract approval = OPEN; route-level Core API enforcement = NOT PROVEN; production activation = NOT AUTHORIZED; P4-REQ-011 = OPEN / NOT PROVEN; Phase 4 exit = BLOCKED.

## Smallest remaining evidence set to close Phase 4

1. Record approved canonical production target and OIDC contract (issuer, audience, JWKS, subject, roles, tenant claim) from authoritative provider/deployment settings.
2. Record trusted membership provisioning and guardian verification authorities, plus approved consent lifecycle/expiry and privacy/audit retention rules.
3. Reconcile PR #122 and #123 into one reviewed migration/repository path without duplicate schema definitions.
4. Integrate authorization into the actual `backend.main:app` routes and nested-resource access paths; tests must prove unauthenticated, wrong-role, cross-tenant, wrong-owner, and missing/revoked/expired/mismatched-consent requests cannot read or mutate protected resources.
5. Run durable PostgreSQL tests and route-level regression on the exact final commit; then separately authorize and execute controlled read-only runtime verification against the confirmed production target.
6. Independent retest must cite exact commit and workflow URLs before P4-REQ-011 can close.

No production schema, configuration, secrets, or live records were changed by this checkpoint.


## Static Core route exposure checkpoint — 2026-10-12

Reviewed `backend/main.py` at source blob `1074d802e1643f303bcd84b48cc5018d19d00976` on the Phase 4 candidate branch. Representative handler signatures for `POST /api/v1/athletes`, `GET /api/v1/athletes/{athlete_id}`, `PATCH /api/v1/athletes/{athlete_id}`, `POST /api/v1/assessments`, and `GET /api/v1/assessments/{assessment_id}` do not declare a verified-principal dependency. `recorded_by` is caller-supplied attribution, not authenticated identity. This is static code review only; no live endpoint was probed.

This confirms route-level enforcement is a substantive remaining gap, not merely missing production configuration. Full acceptance must include every included router and nested-resource chain, server-derived academy/resource ownership, deny-by-default consent checks where applicable, and durable authorization audit. Route tests must demonstrate deny/no mutation for missing/invalid identity, wrong role, wrong tenant/owner, missing/revoked/expired/mismatched consent, and audit persistence failure.

Follow-up comments were posted on [PR #122](https://github.com/hazemwahdan-spec/kaizo-system-/pull/122) and [PR #123](https://github.com/hazemwahdan-spec/kaizo-system-/pull/123) to preserve the safety boundary and require schema reconciliation. Both remain draft candidates; neither should be independently merged or applied.

**Disposition unchanged:** isolated CI = PASS; Gate A = OPEN; route-level enforcement = NOT PROVEN; production activation = NOT AUTHORIZED; P4-REQ-011 = OPEN / NOT PROVEN; Phase 4 exit = BLOCKED.

## Fresh HEAD verification checkpoint — 2026-10-12

- Current PR #122 head verified from GitHub metadata: `4cdfc31e9bd935bef46d929f5a9e3adae07bfac4` (open, draft, mergeable; not merged).
- PR-triggered workflows attached to this exact HEAD completed successfully: Phase 7 Identity RBAC Boundary run [38203917015](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38203917015), Phase 4 Live Runtime Smoke run [38203917155](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38203917155), Persistence Adapter Validation run [38203916969](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38203916969), plus the listed product/runtime/security contract workflows in the same run batch.
- Source reinspection of `backend/main.py` confirms the current top-level athlete and assessment handlers still accept no verified-principal dependency in their function signatures; actor fields such as `recorded_by` / `attached_by` are client-supplied attribution, not authentication. The app also includes feature routers whose route-level protection must be inventoried separately.
- Therefore these green workflows are useful CI evidence only. They do not establish protected route coverage, tenant ownership enforcement, guardian verification, consent checks, or production isolation.
- No production target/provider settings, schema, secrets, or live data were changed in this checkpoint. Canonical production target still requires explicit confirmation because the project history contains both FastAPI Cloud and Railway deployment evidence.
- Disposition unchanged: Gate A OPEN; P4-REQ-011 OPEN / NOT PROVEN; production activation NOT AUTHORIZED; Phase 4 EXIT BLOCKED.

