"""Fail-closed tenant/resource policy for Phase 4 domain runtimes.

Authentication is necessary but not sufficient: this dependency rejects caller-
asserted actor/tenant identities and requires every referenced persisted resource
to have a canonical tenant binding. It deliberately fails closed when PostgreSQL
or ownership evidence is unavailable. Core athlete resources additionally pass
the existing guardian-consent authorization policy.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request

import persistence
from phase4_identity_boundary import Principal, require_phase4_principal
from phase4_tenant_consent import Phase4AuthorizationUnavailable, authorize_resource_access

_ACTOR_FIELDS = (
    "actor_id", "created_by", "owner_id", "changed_by", "requested_by", "user_id",
    "recorded_by", "assessed_by", "decided_by", "reviewed_by", "traced_by",
    "linked_by", "assigned_by", "reported_by", "uploaded_by", "author_id",
)
_RESOURCE_FIELDS = {
    "athlete_id": "athlete", "academy_id": "academy", "item_id": "knowledge",
    "group_id": "academy_group", "knowledge_id": "knowledge",
    "event_id": "competition_event", "report_id": "report",
    "subject_id": None, "entity_id": "digital_twin",
    "assessment_id": "assessment", "decision_id": "decision",
    "membership_id": "academy_membership", "assignment_id": "academy_assignment",
    "resource_id": None,
}


def _payload_resource_ids(request: Request, payload: dict[str, Any]) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for key, resource_type in _RESOURCE_FIELDS.items():
        value = request.path_params.get(key) or payload.get(key) or request.query_params.get(key)
        if value is None or not str(value).strip():
            continue
        inferred = resource_type
        if key == "subject_id":
            subject_type = str(payload.get("subject_type") or "").strip().lower()
            inferred = {"athlete": "athlete", "player": "athlete", "academy": "academy",
                        "knowledge": "knowledge", "competition_event": "competition_event",
                        "event": "competition_event"}.get(subject_type)
            if inferred is None and persistence.is_postgres_enabled():
                # A bare subject_id is accepted only when the persisted athlete
                # repository proves it is an athlete; otherwise deny by default.
                if persistence.get_athlete(str(value)):
                    inferred = "athlete"
        elif key == "resource_id":
            inferred = str(payload.get("resource_type") or "").strip().lower() or None
        if inferred:
            pair = (inferred, str(value))
            if pair not in values:
                values.append(pair)
    return values


def _is_minor_or_unknown(athlete: dict[str, Any]) -> bool:
    from phase4_route_guard import _requires_guardian_consent
    return _requires_guardian_consent(athlete)


def bind_resource_to_tenant_cursor(
    cursor: Any, *, resource_type: str, resource_id: str,
    tenant_id: str, bound_by_subject: str,
) -> None:
    """Persist a resource binding in the caller's transaction with its domain row."""
    cursor.execute(
        """INSERT INTO kaizo_resource_tenant_bindings
           (resource_type, resource_id, tenant_id, bound_by_subject)
           SELECT %s, %s, t.tenant_id, %s
           FROM kaizo_tenants t
           JOIN kaizo_tenant_memberships m ON m.tenant_id=t.tenant_id
           WHERE t.tenant_id=%s AND t.status='ACTIVE'
             AND m.subject_id=%s AND m.status='ACTIVE'
           LIMIT 1""",
        (resource_type, resource_id, bound_by_subject, tenant_id, bound_by_subject),
    )
    if getattr(cursor, "rowcount", 1) != 1:
        raise HTTPException(status_code=403, detail="Active tenant membership is required to bind a resource")


def _allowed_domain_roles(path: str, method: str) -> set[str]:
    """Least-privilege role matrix for domain routes; never infer role from body."""
    method = method.upper()
    if path.startswith("/api/v1/academy/"):
        if path.endswith("/dashboard") or (method == "GET" and "/academies/" in path):
            return {"academy", "coach"}
        return {"academy"}
    if path.startswith("/api/v1/competition/"):
        return {"academy", "coach"} if method not in {"GET", "HEAD"} else {"academy", "coach", "athlete", "parent"}
    if path.startswith("/api/v1/reporting/"):
        if "/export" in path or method not in {"GET", "HEAD"}:
            return {"academy", "coach"}
        return {"academy", "coach", "athlete", "parent"}
    if path == "/api/v1/knowledge/ingest":
        return {"academy", "coach"}
    if path.startswith(("/api/v1/features", "/api/v1/knowledge-runtime",
                        "/api/v1/audit-trace", "/api/v1/evidence-safety")):
        return {"academy", "coach"}
    return set()


async def require_phase4_domain_access(
    request: Request,
    principal: Principal = Depends(require_phase4_principal),
) -> dict[str, Any]:
    """Require verified caller identity plus canonical persisted tenant ownership."""
    allowed_roles = _allowed_domain_roles(request.url.path, request.method)
    if principal.role not in allowed_roles:
        raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": "domain_role_not_authorized"})
    try:
        raw = await request.json()
        payload = raw if isinstance(raw, dict) else {}
    except Exception:
        payload = {}

    for field in _ACTOR_FIELDS:
        supplied = payload.get(field)
        if supplied is not None and str(supplied).strip() != principal.actor_id:
            raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": "actor_identity_mismatch", "field": field})
    supplied_tenant = payload.get("tenant_id") or request.path_params.get("tenant_id")
    if supplied_tenant is not None and str(supplied_tenant) != principal.tenant_id:
        raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": "tenant_mismatch"})
    if not persistence.is_postgres_enabled():
        raise HTTPException(status_code=503, detail="Durable Phase 4 tenant authorization requires PostgreSQL")

    resources = _payload_resource_ids(request, payload)
    # A new knowledge ID may be bound only when neither a binding nor a legacy
    # record exists. Existing unbound records are not silently claimed.
    if request.method.upper() == "POST" and request.url.path in {
        "/api/v1/knowledge-runtime/feat-047/provenance", "/api/v1/knowledge/ingest"
    }:
        knowledge_id = str(payload.get("knowledge_id") or payload.get("item_id") or "").strip()
        if knowledge_id:
            with persistence.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT tenant_id FROM kaizo_resource_tenant_bindings
                           WHERE resource_type='knowledge' AND resource_id=%s LIMIT 1""",
                        (knowledge_id,),
                    )
                    existing_binding = cur.fetchone()
                    cur.execute(
                        "SELECT 1 FROM kaizo_knowledge_repository WHERE item_id=%s",
                        (knowledge_id,),
                    )
                    existing_record = cur.fetchone()
            if existing_binding is None and existing_record is None:
                resources = [item for item in resources if item != ("knowledge", knowledge_id)]
    if not resources:
        # Root resources have no parent binding yet. These explicitly allowlisted
        # creation handlers must write their canonical resource binding in the
        # same transaction as the resource row.
        creation_types = {
            "/api/v1/academy/academies": "academy",
            "/api/v1/competition/events": "competition_event",
            "/api/v1/knowledge-runtime/feat-047/provenance": "knowledge",
            "/api/v1/knowledge/ingest": "knowledge",
        }
        is_tenant_scoped_knowledge_retrieval = (
            request.method.upper() == "POST"
            and request.url.path == "/api/v1/knowledge-runtime/feat-049/retrieve"
        )
        create_resource_type = creation_types.get(request.url.path) if request.method.upper() == "POST" else None
        scope_resource_type = create_resource_type or ("knowledge" if is_tenant_scoped_knowledge_retrieval else None)
        if not scope_resource_type:
            raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": "resource_binding_required"})
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_tenants t
                       JOIN kaizo_tenant_memberships m ON m.tenant_id=t.tenant_id
                       WHERE t.tenant_id=%s AND t.status='ACTIVE'
                         AND m.subject_id=%s AND m.role=%s AND m.status='ACTIVE'
                       LIMIT 1""",
                    (principal.tenant_id, principal.actor_id, principal.role),
                )
                allowed = cur.fetchone() is not None
                cur.execute(
                    """INSERT INTO kaizo_p14_audit_events
                       (actor_subject_id,event_type,tenant_id,resource_type,action,
                        allowed,reason_code,trace_id,metadata)
                       VALUES (%s,'authorization_decision',%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (principal.actor_id, principal.tenant_id, scope_resource_type,
                     f"{request.method.upper()}:{request.url.path}", allowed,
                     ("active_membership_tenant_scoped_operation" if is_tenant_scoped_knowledge_retrieval else "active_membership_create_authorized") if allowed else "active_tenant_membership_missing",
                     request.headers.get("x-trace-id") or request.headers.get("x-request-id"),
                     '{"source":"phase4_domain_authorization","operation":"tenant_scoped_root_operation"}'),
                )
        if not allowed:
            raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": "active_tenant_membership_missing"})
        return {"principal": principal, "tenant_id": principal.tenant_id,
                "resources": [], "create_resource_type": create_resource_type}
    for resource_type, resource_id in resources:
        if resource_type == "athlete":
            athlete = persistence.get_athlete(resource_id)
            if not athlete:
                raise HTTPException(status_code=404, detail="athlete not found")
            try:
                result = authorize_resource_access(
                    principal=principal, tenant_id=principal.tenant_id,
                    resource_type="athlete", resource_id=resource_id,
                    allowed_roles=(principal.role,),
                    action=f"{request.method.upper()}:{getattr(request.scope.get('route'), 'path', request.url.path)}",
                    trace_id=request.headers.get("x-trace-id") or request.headers.get("x-request-id"),
                    child_resource_id=resource_id,
                    requires_guardian_consent=_is_minor_or_unknown(athlete),
                )
            except Phase4AuthorizationUnavailable as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            if not result.get("allowed"):
                raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": result.get("reason_code", "phase4_scope_denied"), "trace_id": result.get("trace_id")})
            continue
        denial: dict[str, Any] | None = None
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_tenants
                       WHERE tenant_id=%s AND status='ACTIVE' LIMIT 1""",
                    (principal.tenant_id,),
                )
                tenant_ok = cur.fetchone() is not None
                cur.execute(
                    """SELECT 1 FROM kaizo_tenant_memberships
                       WHERE tenant_id=%s AND subject_id=%s AND role=%s
                         AND status='ACTIVE' LIMIT 1""",
                    (principal.tenant_id, principal.actor_id, principal.role),
                )
                membership_ok = cur.fetchone() is not None
                for resource_type, resource_id in resources:
                    if not tenant_ok:
                        reason = "tenant_missing_or_inactive"
                    elif not membership_ok:
                        reason = "active_tenant_membership_missing"
                    else:
                        cur.execute(
                            """SELECT 1 FROM kaizo_resource_tenant_bindings
                               WHERE resource_type=%s AND resource_id=%s AND tenant_id=%s LIMIT 1""",
                            (resource_type, resource_id, principal.tenant_id),
                        )
                        reason = "active_membership_and_resource_binding"
                        if cur.fetchone() is None:
                            reason = "resource_tenant_binding_missing_or_mismatched"
                    allowed = reason == "active_membership_and_resource_binding"
                    cur.execute(
                        """INSERT INTO kaizo_p14_audit_events
                           (actor_subject_id,event_type,tenant_id,resource_type,action,
                            allowed,reason_code,trace_id,metadata)
                           VALUES (%s,'authorization_decision',%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                        (principal.actor_id, principal.tenant_id, resource_type,
                         f"{request.method.upper()}:{request.url.path}", allowed, reason,
                         request.headers.get("x-trace-id") or request.headers.get("x-request-id"),
                         '{"source":"phase4_domain_authorization"}'),
                    )
                    if not allowed and denial is None:
                        denial = {"decision": "DENY", "reason_code": reason,
                                  "resource_type": resource_type}
        if denial is not None:
            raise HTTPException(status_code=403, detail=denial)
    return {"principal": principal, "tenant_id": principal.tenant_id, "resources": resources}
