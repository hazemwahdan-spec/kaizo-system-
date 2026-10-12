# Phase 4 Route-Level Identity, Tenant, and P14 Consent Integration

**Date:** 2026-10-12  
**PR:** #125 — draft candidate  
**Requirement:** P4-REQ-011 remains OPEN / NOT PROVEN.

## Integrated route

The actual Core API route `GET /api/v1/athletes/{athlete_id}` now invokes the fail-closed Phase 4 OIDC dependency before loading the athlete record. The authorization repository requires:
- a verified `oidc_jwt` principal;
- active membership for the authenticated subject and role in an active academy tenant;
- a persisted server-side resource-to-tenant binding matching the requested athlete and the principal's tenant;
- for parent-role reads, a verified guardian relationship belonging to that same authenticated guardian and an active, unexpired consent for the exact child, tenant, resource type, and action;
- a durable audit event in the same transaction as the authorization decision.

An absent/mismatched binding or missing/revoked/expired/pending/mismatched consent denies access before the athlete record is loaded. Failure to evaluate durable authorization returns 503 (fail closed). Denial returns 403.

## Test evidence requested in CI

1. Actual `backend.main:app` HTTP tests for identity gate disabled, missing bearer token, cross-tenant/binding mismatch, missing consent, revoked consent, authorization backend failure, and allowed scoped read.
2. PostgreSQL-backed integration tests on disposable CI PostgreSQL for cross-tenant mismatch, missing consent, revoked consent superseding older active consent, one guardian being unable to reuse another guardian's consent, positive scoped consent, and durable audit persistence.
3. Existing Phase 4 smoke, route contract, security regression, and persistence workflows.

## Explicit limits

- This PR integrates the athlete GET route only. Other Core API routes and routers still require route-by-route resource mapping and authorization wiring.
- The additive migration is tested only against disposable CI PostgreSQL. It is not applied to production.
- No existing athlete ownership backfill, guardian verification, Auth0 change, production config change, or production write occurred.
- The new resource binding table must be populated from a verified canonical ownership source before protected records can be read. No tenant is inferred from request-body fields.
- Coach Final Authority is preserved; authorization does not enable autonomous coaching decisions.

## Exit criteria still outstanding

P4-REQ-011 and Phase 4 EXIT cannot close until all in-scope write/read routes are protected, canonical ownership/backfill is reviewed, consent lifecycle is authoritative, controlled production verification is approved and evidenced, and an independent Phase 4 retest passes.
