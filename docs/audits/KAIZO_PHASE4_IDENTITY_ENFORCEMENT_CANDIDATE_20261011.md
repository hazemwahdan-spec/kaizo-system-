# Phase 4 Identity Enforcement Gate — Candidate Implementation

Date: 2026-10-11  
Status: IMPLEMENTATION CANDIDATE — NOT ROUTE-WIRED, NOT PRODUCTION-ACTIVE

## Added

- `backend/phase4_identity_boundary.py`: fail-closed FastAPI dependency primitives that reuse the existing OIDC bearer principal resolver.
- `backend/test_phase4_identity_boundary.py`: tests for default-closed configuration, invalid bearer rejection, verified OIDC principal acceptance, role denial, cross-tenant denial, and matching tenant scope.

## Security behavior

- The enforcement gate is explicitly controlled by `KAIZO_PHASE4_IDENTITY_ENFORCEMENT=oidc`.
- If the gate is absent or disabled, the dependency returns HTTP 503 rather than treating a request as anonymous or accepting actor/role/tenant headers.
- Invalid/missing OIDC bearer credentials return HTTP 401.
- Role or tenant-scope failures return HTTP 403.
- The resource tenant ID must be loaded from the protected resource on the server. It must not be trusted from an unverified request-body field.
- The existing OIDC resolver remains responsible for issuer, audience, JWKS, signature, expiry, and required standard JWT claim validation.

## Deliberately not done

This change does **not** attach the dependency to Phase 4 routes. Wiring it without the complete server-side resource ownership chain, approved consent semantics, and an authorized identity-provider activation would either leave gaps or break the currently served API. No production settings, Auth0 configuration, secrets, or live data were changed.

## Acceptance boundary

The added tests are unit-level enforcement-primitive tests. They are not route-level access-control proof, production identity proof, durable audit proof, or independent Phase 4 exit evidence.

## Required next

1. Complete route-to-resource ownership mapping, including the nested athlete/diagnosis/decision/plan/session relationships.
2. Define where active/revoked/expired minor consent is resolved durably for each applicable child-data action.
3. Wire dependencies to every protected Core and feature route and add HTTP-level negative/positive tests.
4. Obtain separate authorization before setting production OIDC environment variables or enabling the gate.
5. Run controlled live access-denial and authorized-access tests, then independent Phase 4 retest.
