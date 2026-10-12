"""Route-level Phase 4 identity and persisted tenant/consent enforcement."""
from __future__ import annotations

import json
from typing import Any, Mapping
from uuid import uuid4

from fastapi import HTTPException

from phase4_identity_boundary import require_phase4_principal
import persistence

from phase4_tenant_consent import (
    Phase4AuthorizationUnavailable,
    authorize_resource_access,
)


def create_athlete_with_tenant(principal: Any, athlete: Mapping[str, Any]) -> None:
    """Atomically persist an athlete and its server-derived tenant binding."""
    if principal.role not in {"coach", "academy"}:
        raise HTTPException(status_code=403, detail="Role is not authorized to create athletes")
    if not principal.verified or principal.source != "oidc_jwt":
        raise HTTPException(status_code=401, detail="Verified OIDC identity required")
    if not persistence.is_postgres_enabled():
        raise HTTPException(
            status_code=503,
            detail="Durable tenant binding requires PostgreSQL",
        )
    try:
        persistence.initialize()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1
                       FROM kaizo_tenant_memberships m
                       JOIN kaizo_tenants t ON t.tenant_id=m.tenant_id
                       WHERE m.tenant_id=%s AND m.subject_id=%s
                         AND m.role = ANY(%s) AND m.status='ACTIVE'
                         AND t.status='ACTIVE'
                       LIMIT 1""",
                    (principal.tenant_id, principal.actor_id, [principal.role]),
                )
                if cur.fetchone() is None:
                    raise HTTPException(
                        status_code=403,
                        detail="Active academy membership is required",
                    )
                cur.execute(
                    """INSERT INTO kaizo_athletes
                       (athlete_id,display_name,status,metadata,created_at,updated_at)
                       VALUES (%s,%s,%s,%s::jsonb,%s,%s)""",
                    (
                        athlete["athlete_id"], athlete["display_name"], athlete["status"],
                        json.dumps(athlete.get("metadata", {})),
                        athlete["created_at"], athlete["updated_at"],
                    ),
                )
                cur.execute(
                    """INSERT INTO kaizo_resource_tenant_bindings
                       (resource_type,resource_id,tenant_id,bound_by_subject)
                       VALUES ('athlete',%s,%s,%s)""",
                    (athlete["athlete_id"], principal.tenant_id, principal.actor_id),
                )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Athlete and academy binding could not be persisted atomically",
        ) from exc


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


__all__ = ["require_phase4_principal", "enforce_athlete_access", "create_athlete_with_tenant"]
