# KAIZO Phase 7 — OIDC Authentication and Authorization Integration Boundary

## Purpose

Provide a real server-side authentication and authorization boundary for the commercial product API. A verified JWT establishes identity; it does **not** by itself grant an administrative action.

## Auth0 API trust configuration

The Auth0 API must use the exact audience configured by KAIZO:

- API Identifier / audience: `https://api.kaizo.system`
- Issuer: `https://kaizo-system.us.auth0.com/`
- JWKS: `https://kaizo-system.us.auth0.com/.well-known/jwks.json`
- Signing algorithm accepted by KAIZO: RS256
- Access token must be a JWT intended for the KAIZO API (not an ID token).

In Auth0 API Settings, enable both **RBAC** and **Add Permissions in the Access Token**. The second setting is required because KAIZO reads the standard Auth0 `permissions` array from the verified access token. Role strings and custom claims are not substitutes for permissions.

## Required token claims

- `sub`: immutable Auth0 subject; becomes `Principal.actor_id`.
- `iss`, `aud`, `exp`: validated by the JWT verifier.
- `https://kaizo.system/kaizo_role`: KAIZO identity class (`academy`, `coach`, `athlete`, `parent`, `publisher`).
- `https://kaizo.system/tenant_id`: tenant from trusted server-managed identity data.
- `https://kaizo.system/resource_owner_id`: optional resource-owner scope.
- `permissions`: Auth0-issued array of exact permission identifiers. Missing permissions means no Academy permissions.

The role and tenant custom claims must be populated only from trusted Auth0 server-side data (for example, protected `app_metadata`) by a Post Login Action. Do not source them from `user_metadata`, request headers, query parameters, or client-editable profile fields. Do not accept an ID token as an API bearer token.

## Academy permission vocabulary

These exact, case-sensitive identifiers are enforced by KAIZO:

| Permission | Purpose |
|---|---|
| `academy:read` | Read the authenticated Coach's active Academy choices and minimal assigned roster |
| `academy:tenant:bind` | Bind an existing Academy to the signed tenant; `academy` role only |
| `academy:membership:manage` | Create, suspend, reactivate, or revoke Coach membership, subject to database delegation hierarchy |
| `academy:athlete:enroll` | Enrol an athlete in an Academy, subject to primary-owner FK and manager authorization |
| `academy:coach:assign` | Assign a Coach to an enrolled athlete, subject to active membership and manager authorization |

No wildcard or prefix matching is performed. `academy:manage`, `admin`, and role names alone grant none of these permissions.

### Authorization composition

A privileged request is allowed only when all applicable checks pass:

1. Valid RS256 JWT signature, issuer, audience, expiry and subject.
2. Verified `kaizo_role` and tenant claims; tenant is never read from client headers.
3. Exact required permission appears in the verified token's `permissions` array.
4. The operation's role gate passes (`academy` for tenant binding; `academy` or eligible Coach manager for Academy mutations).
5. For Coach managers, the active Academy membership and database delegation hierarchy allow the target role/action.
6. Tenant/Academy/athlete relationships pass their PostgreSQL constraints and scope checks.
7. The mutation and tenant audit event commit in the same transaction.

An Auth0 permission is necessary but not sufficient. In particular, a Coach with `academy:membership:manage` cannot manage a peer or higher membership role, and cannot cross tenant or Academy boundaries.

## Auth0 configuration checklist (manual dashboard work)

1. Open Applications → APIs → the KAIZO Core API (`https://api.kaizo.system`).
2. Enable **RBAC**.
3. Enable **Add Permissions in the Access Token**.
4. Add the five exact permission identifiers above to the API.
5. Assign permissions to narrowly scoped Auth0 roles/users through the approved identity-governance process; do not grant all five by default.
6. Configure the Post Login Action to emit the namespaced role and tenant claims from protected server-managed data.
7. Obtain a fresh Access Token after changes and inspect its decoded claims locally; never paste production tokens into tickets, source code, or chat.
8. Verify positive and negative tokens against the staging API before any production activation.

No Auth0 tenant or production setting is changed by this repository PR. The checklist is a configuration contract, not evidence that the dashboard has been updated.

## KAIZO implementation

- `Principal.permissions` is populated only from the verified JWT `permissions` array.
- `principal_has_permission` requires `verified=true`, `source=oidc_jwt`, and an exact permission match.
- Development/header identities have no trusted permissions.
- Academy read routes require `academy:read`.
- The Academy mutation service wrappers require the corresponding permission above before opening a write transaction.
- Missing or malformed permission claims fail closed.
- Existing Coach Final Authority remains unchanged; all responses retain `execution_authorized=false`.

## Safety and production gate

No Academy write API routes are mounted by this change. The service-level mutation wrappers are permission-gated but remain unavailable as public write endpoints. Existing legacy Academy Ops routes remain fail-closed (HTTP 410).

Production activation remains gated until the Auth0 dashboard configuration is independently verified, real positive/negative JWT tests pass against staging, tenant isolation and durable audit are evidenced, and live dependency/runtime checks are complete.
