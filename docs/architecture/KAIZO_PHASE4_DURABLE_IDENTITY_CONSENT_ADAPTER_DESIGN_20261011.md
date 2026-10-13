# KAIZO Phase 4 — Durable Identity, Tenant and Consent Adapter Design

**Date:** 2026-10-11  
**Related:** P4-REQ-011, PR #122, P13 Identity/RBAC, P14 Minor Consent, P05 durable persistence  
**Status:** Design contract for review — not runtime implementation, not production authorization  
**Evidence rule:** Evidence Before Claim

## 1. Purpose and non-goals

Define the minimum persistence and request-boundary contract needed before Phase 4 Core API routes can be safely protected. Reuse the existing OIDC principal resolver, identity/RBAC boundary, PostgreSQL adapter and P14 consent charter. Do not create a parallel identity provider, infer guardian identity from a role, change the frozen Core Reference, or authorize autonomous training execution.

## 2. Authoritative policy constraints

- Authentication establishes a verified actor; request-body fields such as `created_by`, `coach_id`, `guardian_id`, and `tenant_id` are not identity proof.
- P13 RBAC answers whether the verified actor may perform an action.
- P14 independently answers whether child-data access is permitted for the exact child + verified guardian relationship + academy/tenant + resource + action.
- Consent states are `pending`, `active`, `revoked`, and `expired`; only an active, unexpired, scope-matching consent can permit the applicable action.
- Nested resource scope must be derived from persisted server-side relationships, never a client-provided tenant field.
- Privileged actions and allow/deny decisions require durable audit records.
- Coach Final Authority remains mandatory; execution stays unauthorized by default.

## 3. Durable storage contract (candidate schema)

The following is a design target to validate against the canonical database/migration conventions before implementation; it is not a migration applied to any environment.

### `kaizo_tenant_memberships`
- `membership_id` primary key
- `actor_id` verified OIDC subject
- `academy_id` canonical tenant identifier
- `role` constrained to the approved role vocabulary
- `resource_owner_id` nullable only where the approved role model permits it
- `status` (active/revoked)
- `created_at`, `updated_at`
- Uniqueness/indexes on actor + academy + role + membership status as required by query patterns

Membership data must be provisioned through a trusted administrative path; no self-asserted membership from request payloads.

### `kaizo_guardian_relationships`
- `relationship_id` primary key
- `child_id`, `guardian_actor_id`, `academy_id`
- `verification_status` (pending/verified/revoked)
- `verified_by` nullable until verified
- `verified_at` nullable until verified
- `created_at`, `updated_at`
- Index child + guardian + academy + status

A parent/guardian role alone never establishes a relationship. The authoritative verification process and source of proof must be approved before this table is used to allow access.

### `kaizo_child_consents`
- `consent_id` primary key
- `child_id`, `guardian_actor_id`, `academy_id`
- `resource`, `action`
- `state` constrained to pending/active/revoked/expired
- `expires_at` nullable only if policy explicitly allows non-expiring consent
- `recorded_by_actor_id` from verified identity, not request-body attribution
- `created_at`, `updated_at`, `version`
- Index exact scope tuple and active/expiry lookup

Revocation and state transitions must be recorded as immutable audit events; do not erase prior consent history when a new state supersedes it. Whether non-expiring consent is permitted remains subject to approved policy/legal review and must not be assumed by implementation.

### `kaizo_authorization_audit`
- `event_id` primary key
- `occurred_at`, `correlation_id`
- `actor_id`, `actor_role`, `academy_id`
- `resource_type`, `resource_id`, `action`
- `decision` (allow/deny), `reason_code`
- `consent_id` nullable when consent is not applicable
- `policy_version`, `request_route`
- No bearer tokens, secrets, or unnecessary child-sensitive payloads

Audit insertion must be transactionally coupled to the protected mutation where feasible. Denial events must persist even though the protected mutation is not performed. Failure to persist a required audit event must fail closed for protected operations.

## 4. Request decision sequence

1. Resolve a cryptographically verified OIDC principal (issuer, audience, signature, expiry and required claims).
2. Resolve active membership and role for the canonical academy/tenant.
3. Load the target resource and derive ownership from persisted parent records.
4. Apply role permissions and resource assignment/relationship checks.
5. For child-data actions, verify guardian relationship and query consent for the exact child + guardian + academy + resource + action scope; require active and unexpired state.
6. Perform the requested operation only after every required check passes.
7. Persist a correlation-linked allow/deny audit event; preserve decision provenance and Coach Final Authority.
8. Return no cross-tenant existence or sensitive-data leakage on denials.

## 5. Route coverage requirements

Coverage must include read and write routes, nested resource routes, and feature routers—not only the main decision loop. At minimum inventory and test:
- athlete, assessment, evidence attachment, KPI capture and state snapshot;
- problem statement, diagnosis, candidate generation, rationale, comparison, coach review and decision record;
- training plan, session and dosage;
- digital-twin sync, decision loop/adapt;
- FEAT-033–040, FEAT-042–050 and FEAT-057–060 routers;
- consent-management routes themselves, which require verified guardian/administrative authority and durable audit.

For nested paths, authorization scope is obtained by loading the persisted chain (e.g. session → plan → athlete → academy), then checking the verified principal against that derived scope.

## 6. Acceptance tests before route activation

- Missing bearer, malformed/expired token, wrong issuer/audience/signature → 401; no protected mutation.
- OIDC provider settings absent while the enforcement gate is enabled → fail closed; no protected mutation.
- Valid identity but unsupported role, inactive membership, wrong academy or unassigned coach → 403; no cross-tenant read/write leakage.
- Parent without a verified child relationship → 403.
- Missing/pending/revoked/expired consent or mismatch in child/guardian/academy/resource/action → deny; no protected mutation.
- Matching identity, active membership, authorized role, verified relationship and applicable active consent → only the scoped action is allowed.
- Every deny, consent transition and privileged mutation produces durable audit with correlation ID and reason.
- Restart/redeploy does not erase memberships, relationships, consent history or audit events.
- Tests run against the actual `backend.main:app` and registered feature routers, not only an isolated test FastAPI app.
- Coach override retains original candidate, reason, provenance and outcome lineage; no path authorizes autonomous execution.

## 7. Ordered implementation gates

**Gate A — contract approval:** Confirm canonical tenant/academy identifier, membership provisioning authority, guardian verification source, consent lifecycle rules, resource/action vocabulary, retention/deletion rules and canonical production database/runtime.

**Gate B — schema and repository:** Add versioned migrations and repository methods; test constraints, transaction behavior, concurrency, revocation, expiry and audit durability against ephemeral PostgreSQL.

**Gate C — route enforcement:** Attach the shared verified-principal dependency to the complete protected route inventory, derive scope server-side, integrate durable P14 checks only where applicable, and test the real Core app.

**Gate D — controlled runtime:** Only after separately approved issuer/audience/JWKS, route/role mapping, database/runtime target and production change authorization; run read-only negative checks first, then narrowly controlled writes and read-back.

**Gate E — independent retest:** Independent Phase 4 security retest, exact commit/workflow evidence, no unresolved critical gaps, and a separate explicit exit decision.

## 8. Current decision

This design makes the next implementation work explicit but does not itself satisfy P4-REQ-011. No schema is applied, no production configuration is changed, no consent is treated as verified, and no production write is authorized. Until Gates A–E are evidenced, keep **P4-REQ-011 OPEN / NOT PROVEN** and **Phase 4 EXIT BLOCKED**.
