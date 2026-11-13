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

The additive service layer accepts a Principal only when `verified=true`, `source=oidc_jwt`, the role is `academy` or `coach`, and its tenant matches the operation scope. An Academy Principal must also carry the signed namespaced `https://kaizo.system/academy_id` claim; that claim must exactly match the target Academy, so one tenant containing multiple academies does not imply tenant-wide Academy administrator access. Mutations additionally require explicit Auth0 API permissions: `academy:manage`, `academy:manage_athlete`, or `academy:assign_coach` according to the operation. Membership creation, enrolment, assignment, and lifecycle changes require either that exact Academy Principal or an active `OWNER`/`ADMIN`/`HEAD_COACH` membership. Delegation is hierarchical for both creation and lifecycle changes: `OWNER` may manage `ADMIN`/`HEAD_COACH`/`COACH`/`ASSISTANT`; `ADMIN` may manage `HEAD_COACH`/`COACH`/`ASSISTANT`; `HEAD_COACH` may manage only `COACH`/`ASSISTANT`. Manager and target membership rows are locked inside the same transaction as each mutation. Athlete access requires a verified Coach Principal, the `academy:read` permission, and active membership, enrolment, and assignment. The in-transaction read helper locks those scope rows and must be used in the same transaction as the protected resource read. Development-header principals are rejected. These are service-level checks; no Academy management API routes are mounted by this PR.

Every authenticated mutation wrapper writes `append_tenant_audit` inside the same `persistence.atomic_transaction`. The existing persistence connection context joins nested helpers to the outer transaction, so audit failure rolls back the relationship write. PostgreSQL integration tests exercise this rollback behavior.

## 5. Narrow Product API integration

The branch exposes two read-only routes:
- `GET /api/v1/product/coach/academies` lists only Academies where the verified Coach has an active membership.
- `GET /api/v1/product/coach/academies/{academy_id}/athletes` lists only athletes explicitly assigned to that Coach in the selected Academy.

- Both handlers obtain their Coach Principal through the existing Coach identity boundary, which requires a verified Bearer token and the Auth0 `product` permission; they additionally require `verified=true`, `source=oidc_jwt`, and `academy:read`. Development/header identities are rejected.
- `tenant_id` and `coach_actor_id` are taken only from the verified Principal. Caller-supplied identity headers are not used as authority.
- The requested `academy_id` is a resource selector, not proof of access; the SQL membership and assignment joins must independently authorize the exact Academy.
- The Academy selector uses the same verified tenant/actor and lists only active tenant bindings plus active memberships; it cannot be used to enumerate another tenant's Academy names.
- The SQL query joins tenant binding, active membership, active athlete enrolment, active assignment, and athlete profile. All joins and filters are scoped by the verified tenant, requested academy, and verified Coach subject.
- The response contains only minimal roster fields and explicitly reports `longitudinal_access_granted=false`.
- The selector locks active tenant and membership rows; the roster query locks active tenant, membership, enrolment, and assignment rows for the duration of the read so a concurrent suspension/revocation cannot race the response.
- PostgreSQL is mandatory; if persistence is unavailable, the route returns 503 rather than falling back to memory.
- The route is not yet wired into `frontend/app.js`; it is an API-only boundary and must not be counted as Coach UI integration.
- Existing `/coach/athletes` and longitudinal Product API routes remain primary-owner scoped. No write route or secondary-Coach access to decisions, assessments, training, KPI, audit, or Digital Twin data is introduced.

This is a deliberately narrow first integration, not activation of the legacy Academy Ops router and not completion of the full Academy feature surface.

## 6. Remaining authorization contract before additional routes are enabled

For every Academy read/write:
- Require a verified Bearer OIDC Principal; reject development headers in production.
- Derive `coach_actor_id` from verified `sub`; ignore actor/role/tenant/academy IDs supplied as authority by the browser.
- Derive tenant from verified claims; for Academy-role operations, derive `academy_id` from the signed namespaced claim and require an exact match with the target.
- Verify active `kaizo_tenant_academies` mapping.
- Require explicit `product` plus `academy:read` for the roster endpoint; require the operation-specific `academy:manage`, `academy:manage_athlete`, or `academy:assign_coach` permission for mutations.
- Verify active membership for the exact (tenant, academy, actor) tuple and enforce role-specific permissions.
- For athlete operations, verify active Academy enrolment and active assignment to that authenticated Coach.
- Recheck relationships inside the same PostgreSQL transaction as every write; use row locks where lifecycle changes can race.
- Write an append-only tenant-attributed audit event in the same transaction. Audit failure must roll back the business write.
- Never allow a caller-supplied `coach_final_authority` boolean to grant authority; authority comes from the server-verified Principal and permission policy.
- Keep `execution_authorized=false`; Academy membership never overrides Coach Final Authority.

Required Auth0 API permissions for this boundary: `product` plus `academy:read` for the two GET endpoints; `academy:manage`, `academy:assign_coach`, and `academy:manage_athlete` for the corresponding future mutation operations. The API checks these permissions from the verified token's `permissions` claim. Do not infer permissions from display role strings alone.

## 7. Migration and rollout

- Additive DDL only; no backfill or automatic tenant inference.
- Existing Academy rows remain unbound until an authorized, reviewed mapping operation supplies the true tenant.
- Existing JSONB multi-coach assignments are not auto-converted: their tenant and Coach identity provenance are insufficient.
- Existing Coach ownership rows are retained. Academy enrolment uses a composite FK to the existing (tenant_id, coach_actor_id, athlete_id) unique key and does not create any new uniqueness assumption.
- Keep FEAT-061–065 routes disabled (410) until mapping, identity permissions, atomic audit, and runtime tests are accepted.
- The Academy selector and assigned-roster GET endpoints are the only mounted Academy-aware Product API surfaces; Academy management and all Academy athlete writes remain disabled.
- No production migration, secret mutation, data backfill, or deployment is included in this branch.

## 8. PostgreSQL acceptance matrix

- Same tenant + same academy + active membership + explicit athlete assignment: allow.
- Same tenant + same academy + different Coach without assignment: deny.
- Same tenant + different academy: deny for Coaches without an active assignment and for Academy Principals whose signed `academy_id` names another Academy.
- Different tenant, even with matching Coach/Athlete identifiers: deny.
- Missing or mismatched signed `academy_id` for Academy-role mutation: deny.
- Missing operation permission: deny even when the role string and membership appear valid.
- ADMIN cannot manage OWNER/ADMIN lifecycle; HEAD_COACH cannot manage ADMIN/OWNER lifecycle.
- Academy rebound to another tenant: reject.
- Assignment without active membership: reject.
- Assignment without Academy enrolment: reject by FK.
- Athlete enrolment without matching tenant ownership: reject by FK.
- Revoked/suspended membership or assignment: deny.
- Audit failure: Academy binding, membership creation, enrolment, assignment, and membership lifecycle writes all roll back in their verified Principal service wrappers.
- Concurrent manager revocation/demotion cannot race a mutation because the manager and target memberships are locked in the same transaction.

## 9. Current implementation boundary

This branch adds the normalized schema helper, PostgreSQL isolation tests, and two verified read-only Academy Product API endpoints (Academy selector and assigned-athlete roster). It intentionally does not activate the legacy Academy router or Academy management routes, mutate Auth0 or issue the new Academy permissions/claim, change existing Coach ownership semantics, enable secondary-Coach longitudinal access, wire these Academy endpoints into the Coach UI, or access production databases.
