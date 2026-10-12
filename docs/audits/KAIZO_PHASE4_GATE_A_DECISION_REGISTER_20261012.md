# KAIZO Phase 4 — Gate A Decision Register

Date: 2026-10-12  
Related: P4-REQ-011, PR #122, P13 Identity/RBAC, P14 Minor Consent  
Status: OPEN — decisions below are not approved by this artifact  
Evidence rule: Evidence Before Claim

## Verified evidence at this checkpoint

- PR #122 head: `7bcf574f7a3c1d23af6aa7f7444f80af97188285`.
- Phase 4 Live Runtime Smoke run 38173595370: OpenAPI fetch and health check passed.
- Identity RBAC Boundary run 38173595288: isolated dependency/HTTP contract tests passed.
- Persistence Adapter Validation run 38173595395: ephemeral PostgreSQL and existing acceptance tests passed.
- These checks do not prove actual Core route enforcement, durable guardian verification/consent, or production authorization audit.

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

**Important limitation:** this candidate code does not establish the trusted origin of membership provisioning or guardian verification, is not wired to Core API routes, and has not been applied to any production database. The test fixture's verification actor is test-only. Gate A decisions remain OPEN; Gate B remains **pending CI evidence and contract review**. Do not merge or enable production enforcement based solely on this implementation.


## CI result — 2026-10-12

The candidate persistence implementation at commit `f6ba0a907e6fcbf94b5621b85788dfddfcf5884d` passed the complete Persistence Adapter Validation workflow, including the new **Phase 4 durable identity and consent store acceptance tests**:
- [Persistence Adapter Validation run 38201027285](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201027285) — **SUCCESS**.
- The new test applies the migration only to the workflow's ephemeral PostgreSQL service and covers membership revocation, guardian relationship revocation, exact-scope consent, consent revocation/expiry, and durable deny-audit roundtrip.
- Related identity-boundary tests passed: [run 38201027202](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201027202).
- Limited live smoke passed: [run 38201027300](https://github.com/hazemwahdan-spec/kaizo-system-/actions/runs/38201027300).

This proves the candidate schema/store behavior in CI only. It does **not** prove trusted membership provisioning, real guardian verification, route-level enforcement in `backend.main:app`, production persistence, or live tenant/resource isolation. Therefore Gate B has test evidence for its isolated primitives but remains subject to contract review; Gate A and P4-REQ-011 remain OPEN.
