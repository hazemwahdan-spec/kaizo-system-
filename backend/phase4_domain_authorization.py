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
    "actor_id", "created_by", "owner_id", "changed_by", "requested_by",
    "recorded_by", "assessed_by", "decided_by", "reviewed_by", "traced_by",
    "linked_by", "assigned_by", "reported_by", "uploaded_by", "author_id",
)
_RESOURCE_FIELDS = {
    "athlete_id": "athlete", "academy_id": "academy",
    "group_id": "academy_group", "knowledge_id": "knowledge",
    "event_id": "competition_event", "report_id": "report",
    "subject_id": None, "entity_id": "digital_twin",
    "assessment_id": "assessment", "decision_id": "decision",
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


async def require_phase4_domain_access(
    request: Request,
    principal: Principal = Depends(require_phase4_principal),
) -> dict[str, Any]:
    """Require verified caller identity plus canonical persisted tenant ownership."""
    if principal.role not in {"academy", "coach", "athlete", "parent"}:
        raise HTTPException(status_code=403, detail="Role is not authorized for this domain")
    if not persistence.is_postgres_enabled():
        raise HTTPException(status_code=503, detail="Durable Phase 4 tenant authorization requires PostgreSQL")
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

    resources = _payload_resource_ids(request, payload)
    if not resources:
        raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": "resource_binding_required"})
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
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_resource_tenant_bindings
                       WHERE resource_type=%s AND resource_id=%s AND tenant_id=%s LIMIT 1""",
                    (resource_type, resource_id, principal.tenant_id),
                )
                if cur.fetchone() is None:
                    raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": "resource_tenant_binding_missing", "resource_type": resource_type})
    return {"principal": principal, "tenant_id": principal.tenant_id, "resources": resources}
