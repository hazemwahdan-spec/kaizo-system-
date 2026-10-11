# Phase 4 Digital Brain — Identity, Tenant and Consent Boundary Gap

**Date:** 2026-10-11  
**Requirement:** P4-REQ-011  
**Status:** OPEN / NOT PROVEN — implementation dependency, not a passed requirement  
**Evidence rule:** Absence of evidence is not evidence of a passing control.

## Observed repository evidence

1. The Phase 4 decision path currently lives in Core API handlers in `backend/main.py`, including evidence-linked diagnosis, decision candidates, coach review, decision records, and training plans.
2. The corresponding request models use actor strings such as `diagnosed_by`, `requested_by`, `coach_id`, and `created_by`. The inspected core request/route surface does not show a request-level authentication dependency, `tenant_id` enforcement, or consent check on these decision paths.
3. The separate workflow `.github/workflows/phase-7-identity-rbac-boundary.yml` runs `productization/test_identity.py`, `productization/test_product_api.py`, and `productization/test_product_surface.py`. It is useful evidence for that productization surface, but does not prove the Core API decision handlers above enforce the same boundary.
4. No live identity-provider or tenant-isolation test against the canonical production target is claimed by this record.

## Disposition

P4-REQ-011 is **not passed**. The requirement cannot be marked N/A merely because identity is tracked separately in Phase 7. The integration boundary must be explicitly reconciled before Phase 4 exit.

## Required remediation path

1. Confirm the canonical identity context and trust boundary for Core API requests (reuse the approved identity/RBAC contract; do not create a parallel identity system).
2. Bind authenticated actor/role context to the Phase 4 decision, rationale, coach-review and plan routes. Do not trust a caller-provided actor string as proof of identity.
3. Determine where tenant and consent constraints apply based on the approved data model; do not invent a tenant model or consent semantics in this gap note.
4. Add negative-path acceptance tests for missing/invalid identity, insufficient role, cross-tenant access, and missing required consent where applicable.
5. Verify the same tests against the intended runtime/production target when authorized. CI-only results are not live production proof.

## Scope controls

- Do not change production URLs, secrets, Auth0 settings, or runtime identity mode as part of this documentation change.
- Do not reopen the frozen Core Reference.
- Do not claim Phase 4 exit until the gap is closed with implementation, tests, exact run/commit evidence, and review.
- If the approved architecture explicitly excludes a particular core route from tenant/consent scope, record the authority and rationale rather than assuming it.

**Current resume implication:** continue the independent acceptance work that does not require identity architecture changes, but keep Phase 4 exit blocked on this unresolved requirement until the identity boundary is reconciled.
