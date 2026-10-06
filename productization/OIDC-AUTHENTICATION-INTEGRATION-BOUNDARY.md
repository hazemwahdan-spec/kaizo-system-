# KAIZO Phase 7 — OIDC Authentication Integration Boundary

## Purpose

Provide a real server-side authentication boundary for the commercial product API without pretending that a provider is already connected.

## Production requirements

`KAIZO_IDENTITY_MODE=oidc` requires all three:

- `KAIZO_OIDC_ISSUER`
- `KAIZO_OIDC_AUDIENCE`
- `KAIZO_OIDC_JWKS_URL`

Requests must carry `Authorization: Bearer <JWT>`.

The verifier validates:

- JWT signature using JWKS
- RS256 algorithm
- issuer (iss)
- audience (aud)
- expiry (exp)
- subject (sub)
- KAIZO role claim (kaizo_role or role)
- KAIZO tenant claim (tenant_id or kaizo_tenant_id)

Optional resource_owner_id is read from the verified token.

## Safety

Development header identity remains explicitly unverified and is only suitable for development/test mode.

Production mode fails closed if OIDC is not configured or a token cannot be verified.

This boundary does not claim that a real identity provider has been connected. Production activation still requires live provider verification, server-side RBAC, tenant isolation, durable audit, TLS, monitoring, and end-to-end evidence.
