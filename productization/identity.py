"""KAIZO Phase 7 authentication boundary.

Development headers are explicitly unverified test scaffolding.
Production OIDC mode validates bearer JWTs against the KAIZO production
Auth0 tenant and API audience. Environment variables may override these
public trust settings for an explicitly configured deployment; signature,
issuer, audience and expiry validation always remain mandatory.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

import jwt
from jwt import PyJWKClient


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


VALID_ROLES = {"academy", "coach", "athlete", "parent"}

# Public, deployment-specific OIDC trust configuration. These are not secrets.
# Pinning the expected issuer and audience avoids a fail-open path when the
# hosting platform omits optional environment variables; JWT verification is
# still strict and can be overridden explicitly for another deployment.
DEFAULT_OIDC_ISSUER = "https://kaizo-system.us.auth0.com/"
DEFAULT_OIDC_AUDIENCE = "https://api.kaizo.system"
DEFAULT_OIDC_JWKS_URL = "https://kaizo-system.us.auth0.com/.well-known/jwks.json"


def _oidc_settings() -> tuple[str, str, str]:
    issuer = os.getenv("KAIZO_OIDC_ISSUER", DEFAULT_OIDC_ISSUER).strip()
    audience = os.getenv("KAIZO_OIDC_AUDIENCE", DEFAULT_OIDC_AUDIENCE).strip()
    jwks_url = os.getenv("KAIZO_OIDC_JWKS_URL", DEFAULT_OIDC_JWKS_URL).strip()
    if not issuer or not audience or not jwks_url:
        raise IdentityNotConfiguredError("OIDC issuer, audience and JWKS URL must be configured")
    return issuer, audience, jwks_url


def _claims_to_principal(claims: dict[str, Any]) -> Principal:
    actor_id = claims.get("sub")
    role = claims.get("kaizo_role") or claims.get("role")
    tenant_id = claims.get("tenant_id") or claims.get("kaizo_tenant_id")
    owner = claims.get("resource_owner_id")
    if not actor_id or role not in VALID_ROLES or not tenant_id:
        raise IdentityNotConfiguredError(
            "verified identity is missing required KAIZO claims: sub, role, tenant_id"
        )
    return Principal(
        actor_id=str(actor_id),
        role=str(role),
        tenant_id=str(tenant_id),
        resource_owner_id=str(owner) if owner is not None else None,
        verified=True,
        source="oidc_jwt",
    )


def resolve_bearer_principal(authorization: str | None) -> Principal:
    if not authorization or not authorization.startswith("Bearer "):
        raise IdentityNotConfiguredError("Bearer authentication is required")
    token = authorization[7:].strip()
    if not token:
        raise IdentityNotConfiguredError("Bearer token is empty")

    issuer, audience, jwks_url = _oidc_settings()

    try:
        client = PyJWKClient(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["sub", "iss", "aud", "exp"]},
        )
    except Exception as exc:
        raise IdentityNotConfiguredError(f"OIDC token verification failed: {exc}") from exc

    return _claims_to_principal(claims)

def verify_bearer_token(authorization: str | None) -> dict[str, Any]:
    """Verify an OIDC bearer token using standard JWT claims only."""
    if not authorization or not authorization.startswith("Bearer "):
        raise IdentityNotConfiguredError("Bearer authentication is required")
    token = authorization[7:].strip()
    if not token:
        raise IdentityNotConfiguredError("Bearer token is empty")
    issuer, audience, jwks_url = _oidc_settings()
    try:
        client = PyJWKClient(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            options={"require": ["sub", "iss", "aud", "exp"]},
        )
    except Exception as exc:
        raise IdentityNotConfiguredError(f"OIDC token verification failed: {exc}") from exc
    return {"verified": True, "source": "oidc_jwt", "subject": str(claims["sub"])}


def resolve_principal(
    actor_id: str,
    role: str,
    tenant_id: str,
    resource_owner_id: str | None,
    authorization: str | None = None,
) -> Principal:
    mode = os.getenv("KAIZO_IDENTITY_MODE", "production").strip().lower()

    if mode == "development":
        if not actor_id or not tenant_id or role not in VALID_ROLES:
            raise IdentityNotConfiguredError("development identity headers are incomplete")
        return Principal(
            actor_id=actor_id,
            role=role,
            tenant_id=tenant_id,
            resource_owner_id=resource_owner_id,
            verified=False,
            source="development_headers",
        )

    if mode in {"oidc", "oauth2", "external"}:
        return resolve_bearer_principal(authorization)

    raise IdentityNotConfiguredError(
        "production identity is fail-closed until a real authentication provider is configured"
    )
