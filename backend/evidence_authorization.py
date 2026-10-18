"""Fail-closed authorization for global/shared evidence publishing.

Only a verified OIDC principal carrying the explicit publisher role and the
configured global tenant may use this legacy global evidence API. Academy-owned
evidence must use a separate resource/tenant-scoped route; it is never exposed
through the global list/detail handlers.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import Header, HTTPException

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from productization.identity import IdentityNotConfiguredError, resolve_bearer_principal


GLOBAL_EVIDENCE_SUBJECT_TYPES = frozenset({"rule", "catalog"})


def require_global_evidence_publisher(authorization: str | None = Header(default=None)):
    """Require explicit enablement plus a signed OIDC publisher identity."""
    enabled = os.getenv("KAIZO_EVIDENCE_PUBLISHER_ENABLED", "false").strip().lower()
    if enabled != "true":
        raise HTTPException(
            status_code=503,
            detail="Global evidence publishing is disabled pending publisher-role configuration.",
        )

    try:
        principal = resolve_bearer_principal(authorization)
    except IdentityNotConfiguredError as exc:
        raise HTTPException(
            status_code=401,
            detail="A valid OIDC publisher identity is required.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not principal.verified or principal.source != "oidc_jwt":
        raise HTTPException(status_code=401, detail="Verified OIDC identity required.")

    if principal.role != "publisher":
        raise HTTPException(status_code=403, detail="Global evidence publisher role required.")

    expected_tenant = os.getenv("KAIZO_EVIDENCE_GLOBAL_TENANT_ID", "global").strip()
    if not expected_tenant or principal.tenant_id != expected_tenant:
        raise HTTPException(status_code=403, detail="Global evidence tenant scope denied.")

    return principal
