# KAIZO Phase 7 — Auth0 Live OIDC Integration

## Current provider
Auth0 tenant: `kaizo-system`

Expected issuer:
`https://kaizo-system.us.auth0.com/`

Configured API audience:
`https://api.kaizo.system`

JWT signing algorithm:
`RS256`

## KAIZO production variables

Set these in the KAIZO production environment only after verifying the values in Auth0:

```text
KAIZO_IDENTITY_MODE=oidc
KAIZO_OIDC_ISSUER=https://kaizo-system.us.auth0.com/
KAIZO_OIDC_AUDIENCE=https://api.kaizo.system
KAIZO_OIDC_JWKS_URL=https://kaizo-system.us.auth0.com/.well-known/jwks.json
```

## Important

Do not commit secrets, client secrets, passwords, or bearer tokens.

The Auth0 API and application must be authorized before live token issuance is considered verified.

KAIZO must not claim production activation until a real Auth0-issued JWT has been verified end-to-end against the live KAIZO API.

## Required verified claims

The verified JWT must provide:

- `sub`
- `iss`
- `aud`
- `exp`
- `kaizo_role` or `role`
- `tenant_id` or `kaizo_tenant_id`

Optional:

- `resource_owner_id`

## Evidence gate

This document is integration preparation only.

Production OIDC is CLOSED only when live evidence proves:

1. Auth0 issues a token for the KAIZO Core API audience.
2. KAIZO verifies its signature through Auth0 JWKS.
3. issuer, audience, expiry and required identity claims are accepted.
4. invalid, expired, wrong-audience and wrong-issuer tokens are rejected.
5. server-side RBAC and tenant isolation are enforced using the verified principal.
6. privileged actions produce durable audit evidence.

Until then, production identity remains gated/fail-closed.
