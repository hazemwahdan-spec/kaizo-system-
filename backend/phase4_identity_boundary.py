"""Fail-closed identity dependency primitives for KAIZO Phase 4 routes.

This module is intentionally not wired to production routes yet. Route wiring
requires an approved route/resource map and separately authorized production
identity configuration. Never treat request-body actor fields or development
headers as authentication.
"""
from __future__ import annotations

import os
from typing import Iterable

from fastapi import Header, HTTPException

from productization.identity import (
    IdentityNotConfiguredError,
    Principal,
    resolve_bearer_principal,
)


def require_phase4_principal(
    authorization: str | None = Header(default=None),
) -> Principal:
    """Resolve a verified OIDC principal or fail closed.

    Enforcement is not inferred from the productization header-based test mode.
    The explicit Phase 4 gate must be set to 'oidc' before a bearer principal
    is accepted. A missing/disabled gate yields 503 rather than anonymous access.
    """
    mode = os.getenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "disabled").strip().lower()
    if mode != "oidc":
        raise HTTPException(
            status_code=503,
            detail="Phase 4 identity enforcement is not configured",
        )
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


def require_role(principal: Principal, allowed_roles: Iterable[str]) -> Principal:
    """Enforce an explicit role allowlist after authentication."""
    allowed = frozenset(allowed_roles)
    if principal.role not in allowed:
        raise HTTPException(status_code=403, detail="Role is not authorized")
    return principal


def require_tenant_scope(principal: Principal, resource_tenant_id: str) -> Principal:
    """Deny absent or cross-tenant resource scope; caller must load scope server-side."""
    if not resource_tenant_id or principal.tenant_id != resource_tenant_id:
        raise HTTPException(status_code=403, detail="Tenant scope denied")
    return principal
