# Phase 4 Route / Resource / Consent Integration Findings

Date: 2026-10-11
Status: REVIEW FINDINGS — IMPLEMENTATION STILL OPEN
Related: P4-REQ-011, PR #122, P13 identity/RBAC, P14 minor consent

## Evidence reviewed

- `backend/main.py` on `main`: core athlete, assessment, evidence-linked problem, diagnosis and decision handlers.
- `productization/identity.py`: OIDC JWT verification exists as a reusable resolver, but it is not attached to the Core handlers reviewed.
- `productization/IDENTITY-RBAC-INTEGRATION-BOUNDARY.md`: academy tenant scope, coach/athlete/parent ownership rules, server-side authorization and audit expectations.
- `docs/projects/P14-MINOR-CONSENT-CHARTER-20260930.md` and `docs/audits/P14-MINOR-CONSENT-CLOSURE-20260930.md`.
- `.github/workflows/p14-consent-runtime.yml` and `consent/main.py`.

## Confirmed constraints

1. The Core API uses caller-supplied actor fields such as `recorded_by`, `created_by`, `diagnosed_by`, and `requested_by`. These are attribution fields, not authentication.
2. Several Core handlers resolve linked resources (athlete → assessment → problem statement → diagnosis → candidate/decision) and therefore have a server-side ownership chain that can be used for authorization, but tenant/academy ownership is not consistently present in the returned records in the inspected code.
3. The P14 consent charter requires a separate deny-by-default check scoped to child + guardian + academy + resource + action; pending/revoked/expired or mismatched consent must deny. P13 RBAC remains a separate prerequisite.
4. P14's existing runtime is an in-memory reference implementation: `CONSENTS` and `AUDIT` are process-local lists. Its runtime workflow proves reference policy behavior, not durable production consent state, verified guardian identity, or production authorization.
5. The identity boundary candidate in PR #122 is not wired to routes. Its unit tests and existing CI identity-boundary workflow do not establish Core API HTTP authorization.

## Route/resource mapping rule

For any nested route, load the target resource server-side and derive the athlete/academy/tenant from that persisted record and its parents. Do not accept a request-body tenant, actor, guardian, or owner string as proof of authority.

- Athlete and assessment routes: resolve athlete ownership; assessments must derive athlete through the assessment record.
- Problem statement routes: derive athlete from the problem record and validate the linked assessment belongs to that same athlete.
- Diagnosis routes: derive problem and athlete from the diagnosis/problem records; validate evidence is scoped to the same case.
- Decision candidate, rationale, comparison, coach review and decision record routes: derive diagnosis → problem → athlete; apply explicit coach assignment/academy authorization and preserve Coach Final Authority.
- Training plan/session/dosage routes: derive plan → athlete and session → plan/athlete relationships from persisted records before authorizing changes.
- KPI captures, assessments/evidence, state snapshots, digital-twin sync, decision-loop/adapt and feature routers: inventory every route and resolve ownership before claiming coverage. Do not infer coverage from a passing unrelated workflow.

This is a design mapping for implementation; it is not a claim that these checks currently exist.

## Required acceptance matrix

| Case | Expected result |
|---|---|
| No bearer token on protected route | 401 (or documented fail-closed 503 if provider is not configured); no write |
| Invalid/expired/wrong issuer or audience token | 401; no write |
| Valid token with disallowed role | 403; no write |
| Valid identity but wrong academy/tenant | 403; no read/write leakage |
| Coach not assigned/authorized for athlete/case | 403 |
| Parent without verified relationship | 403 |
| Child data with no/pending/revoked/expired consent | deny; no protected action |
| Active consent but wrong child/guardian/academy/resource/action | deny |
| Correct identity, role, tenant, relationship and applicable active consent | allow only scoped action |
| Every deny/consent change | durable audit event with decision reason and trace/correlation ID |
| Coach review/override | coach final authority preserved; provenance and outcome lineage retained |

## Safe next implementation sequence

1. Add route-level HTTP tests around the actual Core app, first proving the current exposure and then proving each control after wiring.
2. Define one canonical dependency contract using the existing OIDC principal, role allowlists, and server-resolved resource scope; avoid a parallel identity implementation.
3. Add a production-capable consent adapter only after its durable storage and verified guardian relationship contract are defined. Do not wire the current in-memory P14 service as a production authorization oracle.
4. Wire all applicable Core and feature routes, including read routes and indirect/nested resource access; test no-write/no-leak behavior.
5. Keep production activation and live write tests gated until separately authorized. Then run independent Phase 4 retest and record exact commit/run IDs.

## Current disposition

P4-REQ-011 remains OPEN / NOT PROVEN. PR #122 remains an implementation candidate. No production configuration, Auth0 settings, secrets, or live records were changed. Phase 4 exit remains blocked.

## Expanded source route inventory — 2026-10-12

This is a static inventory of route declarations in the current Phase 4 candidate branch, not a runtime route probe. It is intentionally a coverage baseline, not proof that every possible route has been enumerated or secured.

### Top-level Core handlers inspected

- `backend/main.py`: athlete create/read/update; assessment create/read; assessment evidence attach/list; plus further problem, diagnosis, decision and evidence handlers in the same module.
- Representative exposed signatures confirmed by source inspection: `POST /api/v1/athletes`, `GET /api/v1/athletes/{athlete_id}`, `PATCH /api/v1/athletes/{athlete_id}`, `POST /api/v1/assessments`, `GET /api/v1/assessments/{assessment_id}`. They do not declare `Depends(require_phase4_principal)` or another verified-principal dependency. Client-supplied actor labels do not substitute for authenticated identity.

### Included router modules and statically declared paths

- `backend/training_workflow.py`: `POST /feat-033/decision-drill`, `POST /feat-034/drill-prescription`, `POST /feat-035/execution-cues`, `POST /feat-036/training-response`, `POST /feat-037/retest`, `POST /feat-038/before-after`, `POST /feat-039/progress-state`, `POST /feat-040/next-decision-trigger`, `GET /athletes/{athlete_id}`.
- `backend/knowledge_runtime.py`: `POST /feat-047/provenance`, `POST /feat-048/lifecycle`, `POST /feat-049/retrieve`, `POST /feat-050/link`.
- `backend/audit_trace_runtime.py`: `POST /feat-052/trace`, `POST /feat-053/governance`, `POST /feat-054/review`, `POST /feat-055/trace`.
- `backend/evidence_safety_runtime.py`: `POST /feat-057/evidence-quality`, `POST /feat-058/provenance`, `POST /feat-059/block`, `POST /feat-060/escalate`.
- `backend/state_cycle.py`: `POST /feat-042/digital-twin-state`, `GET /feat-042/digital-twin-state/{entity_id}`, `GET /feat-043/state-history/{entity_id}`, `POST /feat-044/decision-state-link`, `GET /feat-044/decision-state-link/{decision_id}`, `POST /feat-045/next-state`.
- `backend/reporting_runtime.py`: `POST /progress`, `POST /kpi-trend`, `POST /coach-summary`, `POST /academy-dashboard`, `POST /export`, `GET /export/{report_id}`.
- `backend/competition_runtime.py`: `POST /events`, `GET /events/{event_id}`, `POST /readiness`, `GET /readiness/{athlete_id}/{event_id}`, `POST /performance`, `GET /trend/{athlete_id}`, `POST /next-decision`.
- `backend/academy_ops_runtime.py`: `POST /academies`, `GET /academies/{academy_id}`, `POST /memberships`, `POST /groups`, `POST /assignments`, `GET /academies/{academy_id}/dashboard`.
- `backend/feature_runtime.py` generates feature routes dynamically via `router.add_api_route`; a decorator-only grep misses these. The router has prefix `/api/v1/features` and registers create, get, and list endpoints per frozen feature ID/slug. All generated routes must be enumerated from the actual FastAPI app/OpenAPI at the exact deployed commit and then checked for dependencies and nested-resource scope.

### Security disposition and next code gate

The inventory confirms that identity enforcement cannot safely be declared complete by testing the standalone dependency in a synthetic `/protected` harness. The next acceptance change must add tests against the actual `backend.main:app` route objects and verify the real registered route dependency graph, then wire approved per-route authorization. Before that wiring can be correct, the contract must specify how tenant scope and resource ownership are derived from persisted records; do not infer academy ownership from request bodies or token claims alone.

FastAPI Cloud is the selected target for current PACK-A/Phase 4 verification. Its attached database and authoritative OIDC issuer/audience/JWKS/claims configuration have not yet been independently verified. No production configuration, migration, or live record was changed by this source inventory.

Current status remains: Gate A partially resolved (hosting target only); Gate B isolated persistence primitives have CI evidence; route-level enforcement NOT PROVEN; P4-REQ-011 OPEN / NOT PROVEN; Phase 4 EXIT BLOCKED.

