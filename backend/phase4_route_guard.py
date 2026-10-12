"""Route-level Phase 4 identity and persisted tenant/consent enforcement."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from phase4_identity_boundary import require_phase4_principal
from phase4_tenant_consent import (
    Phase4AuthorizationUnavailable,
    authorize_resource_access,
)


def enforce_athlete_access(principal: Any, athlete_id: str, action: str) -> None:
    """Enforce actual route access using verified principal + DB-owned scope."""
    if action == "read":
        allowed_roles = {"coach", "academy", "parent"}
    elif action == "update":
        allowed_roles = {"coach", "academy"}
    else:
        raise HTTPException(status_code=403, detail="Action is not authorized")
    if principal.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Role is not authorized")

    # Parent reads require the exact, current guardian relationship and consent.
    requires_consent = action == "read" and principal.role == "parent"
    try:
        result = authorize_resource_access(
            principal=principal,
            tenant_id=principal.tenant_id,
            resource_type="athlete",
            resource_id=athlete_id,
            allowed_roles=[principal.role],
            action=action,
            trace_id=str(uuid4()),
            child_resource_id=athlete_id if requires_consent else None,
            requires_guardian_consent=requires_consent,
        )
    except Phase4AuthorizationUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail="Durable Phase 4 authorization is unavailable",
        ) from exc
    except Exception as exc:
        # Database/schema/runtime failures must never fall through to the record.
        raise HTTPException(
            status_code=503,
            detail="Phase 4 authorization could not be verified",
        ) from exc

    if result.get("allowed") is not True or result.get("audit_persisted") is not True:
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Athlete resource access denied",
                "reason_code": result.get("reason_code", "authorization_not_proven"),
                "trace_id": result.get("trace_id"),
            },
        )


__all__ = ["require_phase4_principal", "enforce_athlete_access"]
