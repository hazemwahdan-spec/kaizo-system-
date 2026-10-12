"""Fail-closed identity dependency for KAIZO Phase 4 Core API routes."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException


class IdentityNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True)
class Principal:
    actor_id: str
    role: str
    tenant_id: str
    resource_owner_id: str | None
    verified: bool
    source: str


def resolve_bearer_principal(authorization: str | None) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise IdentityNotConfiguredError("Bearer authentication is required")
    token = authorization[7:].strip()
    if not token:
        raise IdentityNotConfiguredError("Bearer token is empty")
    issuer = os.getenv("KAIZO_OIDC_ISSUER", "").strip()
    audience = os.getenv("KAIZO_OIDC_AUDIENCE", "").strip()
    jwks_url = os.getenv("KAIZO_OIDC_JWKS_URL", "").strip()
    if not issuer or not audience or not jwks_url:
        raise IdentityNotConfiguredError("OIDC issuer, audience and JWKS must be configured")
    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["sub", "iss", "aud", "exp"]},
        )
    except Exception as exc:
        raise IdentityNotConfiguredError("OIDC token verification failed") from exc

    actor_id = claims.get("sub")
    role = claims.get("kaizo_role") or claims.get("role")
    tenant_id = claims.get("tenant_id") or claims.get("kaizo_tenant_id")
    if not actor_id or role not in {"academy", "coach", "athlete", "parent"} or not tenant_id:
        raise IdentityNotConfiguredError("Verified OIDC token lacks required KAIZO role/tenant claims")
    return Principal(
        actor_id=str(actor_id),
        role=str(role),
        tenant_id=str(tenant_id),
        resource_owner_id=str(claims["resource_owner_id"]) if claims.get("resource_owner_id") else None,
        verified=True,
        source="oidc_jwt",
    )


def require_phase4_principal(authorization: str | None = Header(default=None)) -> Principal:
    if os.getenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "disabled").strip().lower() != "oidc":
        raise HTTPException(status_code=503, detail="Phase 4 identity enforcement is not configured")
    try:
        principal = resolve_bearer_principal(authorization)
    except IdentityNotConfiguredError as exc:
        raise HTTPException(
            status_code=401,
            detail="A valid OIDC bearer identity is required",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    if not principal.verified or principal.source != "oidc_jwt":
        raise HTTPException(status_code=401, detail="Verified OIDC identity required")
    return principal
