"""Server-side resource/tenant authorization for selected Core routes.

This bounded Phase 4 gate requires verified OIDC identity, PostgreSQL-backed
membership/resource ownership, and a durable authorization audit event. Missing
proof or an unavailable audit store denies access.
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, Request

import persistence
from phase4_identity_boundary import require_phase4_principal
from phase4_identity_store import get_resource_tenant, has_active_membership
from productization.identity import Principal


ALLOWED_CORE_ROLES = {"academy", "coach"}
POLICY_VERSION = "phase4-core-v1"


def _audit_authorization(
    *,
    principal: Principal | None,
    resource_type: str,
    resource_id: str | None,
    action: str,
    decision: str,
    reason_code: str,
    request_route: str,
    correlation_id: str | None = None,
) -> None:
    """Persist an allow/deny decision; audit failure itself is fail-closed."""
    from phase4_identity_store import append_authorization_audit

    try:
        append_authorization_audit(
            event_id=str(uuid.uuid4()),
            correlation_id=(correlation_id or str(uuid.uuid4()))[:128],
            actor_id=principal.actor_id if principal else "anonymous",
            actor_role=principal.role if principal else None,
            academy_id=principal.tenant_id if principal else None,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            decision=decision,
            reason_code=reason_code,
            consent_id=None,
            policy_version=POLICY_VERSION,
            request_route=request_route[:512],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Durable authorization audit store is unavailable",
        ) from exc


def require_core_actor(request: Request) -> Principal:
    """Authenticate the request, validate membership, and durably audit the decision."""
    route = request.url.path
    correlation_id = request.headers.get("x-correlation-id")
    try:
        principal = require_phase4_principal(
            authorization=request.headers.get("authorization")
        )
    except HTTPException as exc:
        reason = {
            401: "IDENTITY_INVALID",
            403: "IDENTITY_FORBIDDEN",
            503: "IDENTITY_GATE_UNAVAILABLE",
        }.get(exc.status_code, "IDENTITY_DENIED")
        _audit_authorization(
            principal=None, resource_type="core_route", resource_id=None,
            action="route_access", decision="deny", reason_code=reason,
            request_route=route, correlation_id=correlation_id,
        )
        raise

    if principal.role not in ALLOWED_CORE_ROLES:
        _audit_authorization(
            principal=principal, resource_type="core_route", resource_id=None,
            action="route_access", decision="deny", reason_code="ROLE_NOT_ALLOWED",
            request_route=route, correlation_id=correlation_id,
        )
        raise HTTPException(status_code=403, detail="Core resource role is not authorized")

    try:
        active = has_active_membership(
            actor_id=principal.actor_id,
            academy_id=principal.tenant_id,
            role=principal.role,
        )
    except Exception as exc:
        _audit_authorization(
            principal=principal, resource_type="core_route", resource_id=None,
            action="route_access", decision="deny", reason_code="MEMBERSHIP_STORE_UNAVAILABLE",
            request_route=route, correlation_id=correlation_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Authoritative membership store is unavailable",
        ) from exc

    if not active:
        _audit_authorization(
            principal=principal, resource_type="core_route", resource_id=None,
            action="route_access", decision="deny", reason_code="ACTIVE_MEMBERSHIP_REQUIRED",
            request_route=route, correlation_id=correlation_id,
        )
        raise HTTPException(status_code=403, detail="Active academy membership required")

    _audit_authorization(
        principal=principal, resource_type="core_route", resource_id=None,
        action="route_access", decision="allow", reason_code="IDENTITY_AND_MEMBERSHIP_VALID",
        request_route=route, correlation_id=correlation_id,
    )
    return principal


def assert_resource_tenant(
    *,
    resource_type: str,
    resource_id: str,
    principal: Principal,
    request_route: str = "unknown",
    action: str = "access",
    correlation_id: str | None = None,
) -> None:
    """Check database-owned tenant scope before returning or mutating a resource."""
    try:
        tenant_id = get_resource_tenant(
            resource_type=resource_type, resource_id=resource_id
        )
    except Exception as exc:
        _audit_authorization(
            principal=principal, resource_type=resource_type, resource_id=resource_id,
            action=action, decision="deny", reason_code="RESOURCE_SCOPE_STORE_UNAVAILABLE",
            request_route=request_route,
        )
        raise HTTPException(
            status_code=503,
            detail="Authoritative resource ownership store is unavailable",
        ) from exc

    if not tenant_id or tenant_id != principal.tenant_id:
        _audit_authorization(
            principal=principal, resource_type=resource_type, resource_id=resource_id,
            action=action, decision="deny", reason_code="RESOURCE_TENANT_SCOPE_DENIED",
            request_route=request_route,
        )
        raise HTTPException(status_code=403, detail="Resource tenant scope denied")

    try:
        active = has_active_membership(
            actor_id=principal.actor_id,
            academy_id=tenant_id,
            role=principal.role,
        )
    except Exception as exc:
        _audit_authorization(
            principal=principal, resource_type=resource_type, resource_id=resource_id,
            action=action, decision="deny", reason_code="MEMBERSHIP_STORE_UNAVAILABLE",
            request_route=request_route,
        )
        raise HTTPException(
            status_code=503,
            detail="Authoritative membership store is unavailable",
        ) from exc
    if not active:
        _audit_authorization(
            principal=principal, resource_type=resource_type, resource_id=resource_id,
            action=action, decision="deny", reason_code="ACTIVE_MEMBERSHIP_REQUIRED",
            request_route=request_route,
        )
        raise HTTPException(status_code=403, detail="Active academy membership required")

    _audit_authorization(
        principal=principal, resource_type=resource_type, resource_id=resource_id,
        action=action, decision="allow", reason_code="RESOURCE_TENANT_SCOPE_VALID",
        request_route=request_route,
    )


def assert_assessment_tenant(
    *,
    assessment_id: str,
    principal: Principal,
    request_route: str = "unknown",
    action: str = "read",
) -> str:
    """Resolve assessment -> athlete -> tenant from PostgreSQL before exposing data."""
    if not persistence.is_postgres_enabled():
        _audit_authorization(
            principal=principal, resource_type="assessment", resource_id=assessment_id,
            action=action, decision="deny", reason_code="DURABLE_SCOPE_REQUIRED",
            request_route=request_route,
        )
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
        _audit_authorization(
            principal=principal, resource_type="assessment", resource_id=assessment_id,
            action=action, decision="deny", reason_code="ASSESSMENT_STORE_UNAVAILABLE",
            request_route=request_route,
        )
        raise HTTPException(
            status_code=503,
            detail="Authoritative assessment ownership store is unavailable",
        ) from exc
    if not row:
        _audit_authorization(
            principal=principal, resource_type="assessment", resource_id=assessment_id,
            action=action, decision="deny", reason_code="ASSESSMENT_NOT_FOUND",
            request_route=request_route,
        )
        raise HTTPException(status_code=404, detail="assessment not found")
    athlete_id = str(row[0])
    assert_resource_tenant(
        resource_type="athlete", resource_id=athlete_id, principal=principal,
        request_route=request_route, action=action,
    )
    assert_resource_tenant(
        resource_type="assessment", resource_id=assessment_id, principal=principal,
        request_route=request_route, action=action,
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
        else:
            bind_resource_to_tenant(
                resource_type=resource_type,
                resource_id=resource_id,
                tenant_id=principal.tenant_id,
                bound_by_actor_id=principal.actor_id,
            )
    except Exception as exc:
        _audit_authorization(
            principal=principal, resource_type=resource_type, resource_id=resource_id,
            action="create", decision="deny", reason_code="RESOURCE_BINDING_WRITE_FAILED",
            request_route=f"/api/v1/{resource_type}s",
        )
        raise HTTPException(
            status_code=503,
            detail="Unable to atomically persist Core resource ownership",
        ) from exc

    _audit_authorization(
        principal=principal, resource_type=resource_type, resource_id=resource_id,
        action="create", decision="allow", reason_code="RESOURCE_CREATED_AND_BOUND",
        request_route=f"/api/v1/{resource_type}s",
    )
