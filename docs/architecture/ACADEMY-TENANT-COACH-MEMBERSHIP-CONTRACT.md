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

Current `kaizo_coach_athlete_ownership` stores one primary Coach per athlete: `athlete_id` is the primary key, with `tenant_id + coach_actor_id` as ownership attributes and a composite unique key. The current Coach API correctly scopes its roster by tenant, actor, and athlete.

Current Academy Operations creates separate `kaizo_academies`, `kaizo_academy_memberships`, `kaizo_academy_groups`, and `kaizo_academy_assignments` records. These tables have no `tenant_id`, no FK to Coach ownership, and store multi-coach assignments as JSONB. `coach_id` is caller-supplied data. Its `_audit` helper swallows exceptions and does not use the atomic transaction used by Coach ownership.

The Academy routes are currently fail-closed by the main app's legacy-route boundary (HTTP 410); the Academy Ops runtime's own handlers are not a production authorization contract. Do not mount/activate them as part of this additive schema change.

The Academy P03 charter explicitly excluded production authentication/RBAC and durable longitudinal athlete storage. The P03 closure artifact describes the Academy UI as browser-local, not authoritative durable records. This new contract does not retroactively change those claims.

## 3. Authoritative relationship model

1. `kaizo_tenant_academies`: maps one existing Academy to exactly one Tenant; tenant may map to many academies.
2. `kaizo_academy_coach_memberships`: one membership per (tenant, academy, authenticated Coach subject), with role and lifecycle state.
3. `kaizo_academy_athletes`: explicit athlete enrolment in an academy, FK constrained to the athlete's existing Coach-ownership tenant.
4. `kaizo_academy_athlete_coach_assignments`: normalized multi-Coach assignment; every assigned Coach must have an active membership in that same tenant and academy.

The existing Coach ownership row remains the primary ownership anchor and is not replaced by Academy membership. Academy enrolment stores the explicit primary-owner Coach and uses a composite FK to the existing (tenant_id, coach_actor_id, athlete_id) ownership key. The existing ownership table has athlete_id as its primary key, so the current schema enforces one ownership row per athlete globally; it also declares the composite unique key (tenant_id, coach_actor_id, athlete_id). The new FK explicitly binds enrolment to that ownership Coach and tenant rather than relying on a global athlete ID alone. The service still fails closed if no unambiguous owner row is found. An Academy assignment grants only the Academy-scoped relationship represented here; it does not silently broaden Product API access.

## 4. Verified Principal service boundary now implemented

The additive service layer accepts a Principal-like object only when `verified=true`, `source=oidc_jwt`, the role is `academy` or `coach`, and its tenant matches the operation scope. Tenant binding requires the signed `academy` role. Membership creation, athlete enrolment, assignment, and membership lifecycle changes require either that Academy role or an active `OWNER`/`ADMIN`/`HEAD_COACH` membership. Delegation is hierarchical: `OWNER` may grant `ADMIN`/`HEAD_COACH`/`COACH`/`ASSISTANT`; `ADMIN` may grant `HEAD_COACH`/`COACH`/`ASSISTANT`; `HEAD_COACH` may grant only `COACH`/`ASSISTANT`. Coach actors cannot create or revoke `OWNER` memberships; only the signed Academy role can do so. Athlete access checks require a verified Coach Principal and an active membership plus active enrolment and assignment. Development-header principals are rejected. These service-level checks remain the authorization foundation for the narrow read endpoint described below.

Every authenticated mutation wrapper writes `append_tenant_audit` inside the same `persistence.atomic_transaction`. The existing persistence connection context joins nested helpers to the outer transaction, so audit failure rolls back the relationship write. PostgreSQL integration tests exercise this rollback behavior. Manager membership and target membership are re-read under row locks inside that same transaction, closing the check-then-write race. Lifecycle changes use the same delegation matrix as grants: OWNER may manage ADMIN/HEAD_COACH/COACH/ASSISTANT; ADMIN may manage HEAD_COACH/COACH/ASSISTANT; HEAD_COACH may manage COACH/ASSISTANT. A Coach cannot suspend, revoke, or reactivate a peer or higher role. The signed Academy role remains the only path to OWNER lifecycle administration.

## 5. Narrow Product API integration

The branch now exposes two read-only routes:
- `GET /api/v1/product/coach/academies`: lists only active Academy memberships of the verified Coach.
- `GET /api/v1/product/coach/academies/{academy_id}/athletes`: lists only active athlete assignments for that Coach in the selected Academy.

- The handler obtains its Coach Principal through the existing Coach identity boundary and additionally requires `verified=true` and `source=oidc_jwt`; development/header identities are rejected.
- `tenant_id` and `coach_actor_id` are taken only from the verified Principal. Caller-supplied identity headers are not used as authority.
- The SQL query joins tenant binding, active membership, active athlete enrolment, active assignment, and athlete profile. All joins and filters are scoped by the verified tenant, requested academy, and verified Coach subject.
- The response contains only minimal roster fields and explicitly reports `longitudinal_access_granted=false`.
- PostgreSQL is mandatory; if persistence is unavailable, either route returns 503 rather than falling back to memory.
- Coach UI now loads the verified Coach's Academy memberships, lets the Coach select an Academy, and displays only the minimal assigned roster. It does not navigate secondary-assigned athletes into the primary-owner longitudinal workspace.
- Existing `/coach/athletes` and longitudinal Product API routes remain primary-owner scoped. No write route or secondary-Coach access to decisions, assessments, training, KPI, audit, or Digital Twin data is introduced.

This is a deliberately narrow first integration, not activation of the legacy Academy Ops router and not completion of the full Academy feature surface.

## 6. Remaining authorization contract before additional routes are enabled

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

## 7. Migration and rollout

- Additive DDL only; no backfill or automatic tenant inference.
- Existing Academy rows remain unbound until an authorized, reviewed mapping operation supplies the true tenant.
- Existing JSONB multi-coach assignments are not auto-converted: their tenant and Coach identity provenance are insufficient.
- Existing Coach ownership rows are retained. Academy enrolment uses a composite FK to the existing (tenant_id, coach_actor_id, athlete_id) unique key and does not create any new uniqueness assumption.
- Keep FEAT-061–065 routes disabled (410) until mapping, identity permissions, atomic audit, and runtime tests are accepted.
- The read-only assigned-roster endpoint is the only mounted Academy-aware Product API surface; Academy management and all athlete writes remain disabled.
- No production migration, secret mutation, data backfill, or deployment is included in this branch.

## 8. PostgreSQL acceptance matrix

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

## 9. Current implementation boundary

This branch adds the normalized schema helper, PostgreSQL isolation tests, and one verified read-only Academy-assigned roster endpoint. It intentionally does not activate the legacy Academy router, mutate Auth0, change existing Coach ownership semantics, enable secondary-Coach longitudinal access, or access production databases.
