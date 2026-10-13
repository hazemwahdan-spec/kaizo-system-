"""Server-side resource/tenant authorization for selected Core routes.

This is an incremental Phase 4 gate. It requires verified OIDC identity and
PostgreSQL-backed membership/resource bindings; absence of proof denies access.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

import persistence
from phase4_identity_boundary import require_phase4_principal
from phase4_identity_store import get_resource_tenant, has_active_membership
from productization.identity import Principal


ALLOWED_CORE_ROLES = {"academy", "coach"}


def require_core_actor(
    principal: Principal = Depends(require_phase4_principal),
) -> Principal:
    if principal.role not in ALLOWED_CORE_ROLES:
        raise HTTPException(status_code=403, detail="Core resource role is not authorized")
    try:
        active = has_active_membership(
            actor_id=principal.actor_id,
            academy_id=principal.tenant_id,
            role=principal.role,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authoritative membership store is unavailable",
        ) from exc
    if not active:
        raise HTTPException(status_code=403, detail="Active academy membership required")
    return principal


def assert_resource_tenant(
    *, resource_type: str, resource_id: str, principal: Principal,
) -> None:
    """Check a database-owned binding before returning or mutating the resource."""
    try:
        tenant_id = get_resource_tenant(
            resource_type=resource_type, resource_id=resource_id
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authoritative resource ownership store is unavailable",
        ) from exc
    if not tenant_id or tenant_id != principal.tenant_id:
        raise HTTPException(status_code=403, detail="Resource tenant scope denied")
    # Recheck current membership at the resource's authoritative tenant.
    try:
        active = has_active_membership(
            actor_id=principal.actor_id,
            academy_id=tenant_id,
            role=principal.role,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authoritative membership store is unavailable",
        ) from exc
    if not active:
        raise HTTPException(status_code=403, detail="Active academy membership required")


def assert_assessment_tenant(*, assessment_id: str, principal: Principal) -> str:
    """Resolve assessment -> athlete -> tenant from PostgreSQL before exposing data."""
    if not persistence.is_postgres_enabled():
        raise HTTPException(status_code=503, detail="Durable resource scope is required")
    try:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT athlete_id FROM kaizo_assessments WHERE assessment_id=%s",
                    (assessment_id,),
                )
                row = cur.fetchone()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authoritative assessment ownership store is unavailable",
        ) from exc
    if not row:
        raise HTTPException(status_code=404, detail="assessment not found")
    athlete_id = str(row[0])
    assert_resource_tenant(
        resource_type="athlete", resource_id=athlete_id, principal=principal
    )
    assert_resource_tenant(
        resource_type="assessment", resource_id=assessment_id, principal=principal
    )
    return athlete_id


def bind_new_resource(
    *,
    resource_type: str,
    resource_id: str,
    principal: Principal,
    resource_data: dict | None = None,
) -> None:
    """Persist ownership with the Core resource in one transaction when data is supplied."""
    from phase4_identity_store import bind_resource_to_tenant

    try:
        if resource_data is not None:
            if resource_data.get("athlete_id") != resource_id and resource_data.get("assessment_id") != resource_id:
                raise ValueError("Resource payload identity does not match binding identity")
            persistence.persist_core_resource_and_binding(
                resource_type=resource_type,
                resource=resource_data,
                tenant_id=principal.tenant_id,
                bound_by_actor_id=principal.actor_id,
            )
            return
        bind_resource_to_tenant(
            resource_type=resource_type,
            resource_id=resource_id,
            tenant_id=principal.tenant_id,
            bound_by_actor_id=principal.actor_id,
        )
    except Exception as exc:
        # Fail closed: caller must not return success if ownership cannot be recorded.
        raise HTTPException(
            status_code=503,
            detail="Unable to atomically persist Core resource ownership",
        ) from exc
