"""Route-level Phase 4 guard for the Core API decision workflow.

This dependency uses verified OIDC claims only for identity, then independently
checks active academy membership and the persisted athlete->academy binding.
Child/unknown-age records fail closed unless an exact, active P14 consent scope
and verified guardian relationship exist. It never trusts request actor IDs as
identity or request tenant labels as ownership.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import HTTPException, Request

import persistence
from phase4_identity_boundary import require_phase4_principal
from phase4_tenant_consent import (
    Phase4AuthorizationUnavailable,
    authorize_resource_access,
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _age_from_athlete(athlete: dict[str, Any]) -> int | None:
    metadata = _as_dict(athlete.get("metadata"))
    raw = (
        athlete.get("date_of_birth")
        or athlete.get("birth_date")
        or metadata.get("date_of_birth")
        or metadata.get("birth_date")
    )
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        born = date.fromisoformat(raw[:10])
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except ValueError:
        return None


def _requires_guardian_consent(athlete: dict[str, Any]) -> bool:
    metadata = _as_dict(athlete.get("metadata"))
    if metadata.get("is_minor") is True:
        return True
    age = _age_from_athlete(athlete)
    # Unknown age is not proof of adulthood; deny-by-default for child data.
    return age is None or age < 18


def _resolve_athlete_id(request: Request, payload: dict[str, Any]) -> str:
    path = request.path_params
    if path.get("athlete_id"):
        return str(path["athlete_id"])
    if payload.get("athlete_id"):
        return str(payload["athlete_id"])

    if path.get("assessment_id") or payload.get("assessment_id"):
        assessment_id = str(path.get("assessment_id") or payload.get("assessment_id"))
        assessment = persistence.get_assessment(assessment_id)
        if assessment:
            return str(assessment.get("athlete_id") or "")

    if path.get("problem_id") or payload.get("problem_id"):
        problem_id = str(path.get("problem_id") or payload.get("problem_id"))
        problem = persistence.get_problem_statement(problem_id)
        if problem:
            return str(problem.get("athlete_id") or "")

    if path.get("diagnosis_id"):
        rows = persistence.list_evidence_linked_diagnoses_for_id(str(path["diagnosis_id"]))
        if rows:
            return str(rows[0].get("athlete_id") or "")

    if path.get("candidate_id"):
        candidate = persistence.get_decision_candidate(str(path["candidate_id"]))
        if candidate:
            return str(candidate.get("athlete_id") or "")

    raise HTTPException(status_code=403, detail="Persisted athlete ownership could not be resolved")


async def require_phase4_route_access(request: Request) -> dict[str, Any]:
    """Authenticate and authorize a real Core API request before its handler."""
    principal = require_phase4_principal(request.headers.get("authorization"))
    if principal.role not in {"coach", "academy"}:
        raise HTTPException(status_code=403, detail="Role is not authorized for coaching decision data")
    if not persistence.is_postgres_enabled():
        raise HTTPException(status_code=503, detail="Durable Phase 4 authorization requires PostgreSQL")

    try:
        payload = await request.json()
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        payload = {}

    athlete_id = _resolve_athlete_id(request, payload)
    athlete = persistence.get_athlete(athlete_id)
    if athlete is None:
        raise HTTPException(status_code=404, detail="athlete not found")

    route = request.scope.get("route")
    route_template = getattr(route, "path", request.url.path)
    action = f"{request.method.upper()}:{route_template}"
    try:
        result = authorize_resource_access(
            principal=principal,
            tenant_id=principal.tenant_id,
            resource_type="athlete",
            resource_id=athlete_id,
            allowed_roles=("coach", "academy"),
            action=action,
            trace_id=request.headers.get("x-trace-id") or request.headers.get("x-request-id"),
            child_resource_id=athlete_id,
            requires_guardian_consent=_requires_guardian_consent(athlete),
        )
    except Phase4AuthorizationUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not result.get("allowed"):
        raise HTTPException(
            status_code=403,
            detail={
                "decision": "DENY",
                "reason_code": result.get("reason_code", "phase4_scope_denied"),
                "trace_id": result.get("trace_id"),
            },
        )
    return {"principal": principal, "athlete_id": athlete_id, "authorization": result}
