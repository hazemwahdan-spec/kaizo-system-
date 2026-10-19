"""Tenant-scoped audit-read authorization; never trust caller-supplied tenant IDs."""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import Header, HTTPException

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from productization.identity import IdentityNotConfiguredError, resolve_bearer_principal


def require_tenant_audit_reader(authorization: str | None = Header(default=None)):
    """Require a verified OIDC academy principal; tenant comes only from its claims."""
    try:
        principal = resolve_bearer_principal(authorization)
    except IdentityNotConfiguredError as exc:
        raise HTTPException(
            status_code=401,
            detail="A valid OIDC identity is required to read tenant audit logs.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not principal.verified or principal.source != "oidc_jwt":
        raise HTTPException(status_code=401, detail="Verified OIDC identity required.")

    # Until a distinct tenant-admin role exists, only the academy role may read
    # its own tenant's audit trail. No request parameter can override tenant_id.
    if principal.role != "academy":
        raise HTTPException(status_code=403, detail="Tenant audit reader role required.")
    if not isinstance(principal.tenant_id, str) or not principal.tenant_id.strip():
        raise HTTPException(status_code=403, detail="Tenant audit scope is required.")
    return principal
