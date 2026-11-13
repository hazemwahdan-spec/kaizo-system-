# KAIZO Academy / Tenant / Coach Membership Contract

Status: Draft implementation contract — 2026-11-13  
Branch: `feat/academy-tenant-coach-membership-contract-20261113`

## 1. Identity domains are distinct

- `tenant_id`: security/data-isolation partition asserted by a verified OIDC Principal.
- `academy_id`: operational academy identifier. It is not a tenant identifier and is never inferred from one.
- `coach_actor_id`: stable authenticated subject (`sub`) for a Coach. Client-supplied `coach_id` is never authority.
- `membership_id`: durable membership relationship for one Coach in one Academy/Tenant.
- `athlete_id`: stable athlete identity; tenant affiliation and academy enrolment are explicit relationships.

A tenant may own multiple academies. Each academy is bound to exactly one tenant. This is an explicit cardinality decision in the new contract, not an ID equality assumption.

## 2. Existing evidence and root cause

Current `kaizo_coach_athlete_ownership` stores one primary Coach per athlete with `athlete_id` as its primary key and `tenant_id + coach_actor_id` as ownership attributes. The current Coach API correctly scopes its roster by tenant, actor, and athlete.

Current Academy Operations creates separate `kaizo_academies`, `kaizo_academy_memberships`, `kaizo_academy_groups`, and `kaizo_academy_assignments` records. These tables have no `tenant_id`, no FK to Coach ownership, and store multi-coach assignments as JSONB. `coach_id` is caller-supplied data. Its `_audit` helper swallows exceptions and does not use the atomic transaction used by Coach ownership.

The Academy routes are currently fail-closed by the main app's legacy-route boundary (HTTP 410); the Academy Ops runtime's own handlers are not a production authorization contract. Do not mount/activate them as part of this additive schema change.

The Academy P03 charter explicitly excluded production authentication/RBAC and durable longitudinal athlete storage. The P03 closure artifact describes the Academy UI as browser-local, not authoritative durable records. This new contract does not retroactively change those claims.

## 3. Authoritative relationship model

1. `kaizo_tenant_academies`: maps one existing Academy to exactly one Tenant; tenant may map to many academies.
2. `kaizo_academy_coach_memberships`: one membership per (tenant, academy, authenticated Coach subject), with role and lifecycle state.
3. `kaizo_academy_athletes`: explicit athlete enrolment in an academy, FK constrained to the athlete's existing Coach-ownership tenant.
4. `kaizo_academy_athlete_coach_assignments`: normalized multi-Coach assignment; every assigned Coach must have an active membership in that same tenant and academy.

The existing Coach ownership row remains the primary ownership anchor and is not replaced by Academy membership. Academy enrolment stores the explicit primary-owner Coach and uses a composite FK to the existing (tenant_id, coach_actor_id, athlete_id) ownership key. This deliberately avoids assuming that (tenant_id, athlete_id) is globally unique: the existing ownership table permits multiple Coach rows. If the tenant has zero or multiple candidate primary-owner rows for an athlete, the authenticated enrolment service fails closed rather than guessing. An Academy assignment grants only the Academy-scoped relationship represented here; it does not silently broaden Product API access.

## 4. Verified Principal service boundary now implemented

The additive service layer accepts a Principal-like object only when `verified=true`, `source=oidc_jwt`, the role is `academy` or `coach`, and its tenant matches the operation scope. Tenant binding requires the signed `academy` role. Membership creation, athlete enrolment, assignment, and membership lifecycle changes require either that Academy role or an active `OWNER`/`ADMIN`/`HEAD_COACH` membership. Athlete access checks require a verified Coach Principal and an active membership plus active enrolment and assignment. Development-header principals are rejected. These are service-level checks; no Academy API routes are mounted by this PR.

Every authenticated mutation wrapper writes `append_tenant_audit` inside the same `persistence.atomic_transaction`. The existing persistence connection context joins nested helpers to the outer transaction, so audit failure rolls back the relationship write. PostgreSQL integration tests exercise this rollback behavior.

## 5. Required authorization contract before routes are enabled

For every Academy read/write:
- Require a verified Bearer OIDC Principal; reject development headers in production.
- Derive `coach_actor_id` from verified `sub`; ignore actor/role/tenant/academy IDs supplied as authority by the browser.
- Derive tenant from verified claims and verify active `kaizo_tenant_academies` mapping.
- Verify active membership for the exact (tenant, academy, actor) tuple and enforce role-specific permissions.
- For athlete operations, verify active Academy enrolment and active assignment to that authenticated Coach.
- Recheck relationships inside the same PostgreSQL transaction as every write; use row locks where lifecycle changes can race.
- Write an append-only tenant-attributed audit event in the same transaction. Audit failure must roll back the business write.
- Never allow a caller-supplied `coach_final_authority` boolean to grant authority; authority comes from the server-verified Principal and permission policy.
- Keep `execution_authorized=false`; Academy membership never overrides Coach Final Authority.

Suggested permission vocabulary (must be aligned with the Auth0 API contract before use): `academy:read`, `academy:manage`, `academy:assign_coach`, `academy:manage_athlete`. Do not infer permissions from display role strings alone.

## 6. Migration and rollout

- Additive DDL only; no backfill or automatic tenant inference.
- Existing Academy rows remain unbound until an authorized, reviewed mapping operation supplies the true tenant.
- Existing JSONB multi-coach assignments are not auto-converted: their tenant and Coach identity provenance are insufficient.
- Existing Coach ownership rows are retained. Academy enrolment uses a composite FK to the existing (tenant_id, coach_actor_id, athlete_id) unique key; it does not add a potentially invalid uniqueness assumption on (tenant_id, athlete_id).
- Keep FEAT-061–065 routes disabled (410) until mapping, identity permissions, atomic audit, and runtime tests are accepted.
- No production migration, secret mutation, data backfill, or deployment is included in this branch.

## 7. PostgreSQL acceptance matrix

- Same tenant + same academy + active membership + explicit athlete assignment: allow.
- Same tenant + same academy + different Coach without assignment: deny.
- Same tenant + different academy: deny.
- Different tenant, even with matching Coach/Athlete identifiers: deny.
- Academy rebound to another tenant: reject.
- Assignment without active membership: reject.
- Assignment without Academy enrolment: reject by FK.
- Athlete enrolment without matching tenant ownership: reject by FK.
- Revoked/suspended membership or assignment: deny.
- Audit failure: business write rolls back in the verified Principal service wrappers.

## 8. Current implementation boundary

This branch adds the normalized schema helper and PostgreSQL integration tests only. It intentionally does not activate the legacy Academy router, mutate Auth0, change existing Coach ownership semantics, or access production databases.
