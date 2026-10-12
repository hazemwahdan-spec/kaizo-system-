"""Route-level Phase 4 guard for the Core API decision workflow.

This dependency uses verified OIDC claims only for identity, then independently
checks active academy membership and the persisted athlete->academy binding.
Child/unknown-age records fail closed unless an exact, active P14 consent scope
and verified guardian relationship exist. It never trusts request actor IDs as
identity or request tenant labels as ownership.
"""
from __future__ import annotations

from datetime import date
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
    # Age must come from an authoritative top-level persisted field, never
    # user-editable metadata. Unknown age remains consent-required.
    raw = athlete.get("date_of_birth") or athlete.get("birth_date")
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

    # Resolve persisted child records before considering any body-supplied
    # athlete_id, so a request cannot choose a different owner than its parent.
    if path.get("assessment_id") or payload.get("assessment_id"):
        assessment_id = str(path.get("assessment_id") or payload.get("assessment_id"))
        assessment = persistence.get_assessment(assessment_id)
        if not assessment:
            raise HTTPException(status_code=404, detail="assessment not found")
        persisted_athlete_id = str(assessment.get("athlete_id") or "")
        if payload.get("athlete_id") and str(payload["athlete_id"]) != persisted_athlete_id:
            raise HTTPException(status_code=403, detail="Assessment/athlete ownership mismatch")
        return persisted_athlete_id

    if path.get("problem_id") or payload.get("problem_id"):
        problem_id = str(path.get("problem_id") or payload.get("problem_id"))
        problem = persistence.get_problem_statement(problem_id)
        if not problem:
            raise HTTPException(status_code=404, detail="problem statement not found")
        persisted_athlete_id = str(problem.get("athlete_id") or "")
        if payload.get("athlete_id") and str(payload["athlete_id"]) != persisted_athlete_id:
            raise HTTPException(status_code=403, detail="Problem/athlete ownership mismatch")
        return persisted_athlete_id

    if path.get("diagnosis_id"):
        rows = persistence.list_evidence_linked_diagnoses_for_id(str(path["diagnosis_id"]))
        if not rows:
            raise HTTPException(status_code=404, detail="diagnosis not found")
        return str(rows[0].get("athlete_id") or "")

    if path.get("candidate_id"):
        candidate = persistence.get_decision_candidate(str(path["candidate_id"]))
        if not candidate:
            raise HTTPException(status_code=404, detail="decision candidate not found")
        return str(candidate.get("athlete_id") or "")

    # Additional child resources are resolved through their persisted parent records.
    if path.get("plan_id") or payload.get("plan_id"):
        plan_id = str(path.get("plan_id") or payload.get("plan_id"))
        plan = persistence.get_training_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="training plan not found")
        return str(plan.get("athlete_id") or "")

    if path.get("session_id") or payload.get("session_id"):
        session_id = str(path.get("session_id") or payload.get("session_id"))
        session = persistence.get_training_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="training session not found")
        return str(session.get("athlete_id") or "")

    if path.get("dosage_id"):
        dosage = persistence.get_training_dosage(str(path["dosage_id"]))
        if not dosage:
            raise HTTPException(status_code=404, detail="training dosage not found")
        return str(dosage.get("athlete_id") or "")

    if path.get("snapshot_id"):
        snapshot = persistence.get_state_snapshot(str(path["snapshot_id"]))
        if not snapshot:
            raise HTTPException(status_code=404, detail="state snapshot not found")
        return str(snapshot.get("athlete_id") or "")

    if path.get("capture_id"):
        capture = persistence.get_kpi_capture(str(path["capture_id"]))
        if not capture:
            raise HTTPException(status_code=404, detail="KPI capture not found")
        return str(capture.get("athlete_id") or "")

    if path.get("selection_id"):
        selection = persistence.get_problem_library_selection(str(path["selection_id"]))
        if not selection:
            raise HTTPException(status_code=404, detail="problem-library selection not found")
        return str(selection.get("athlete_id") or "")

    if path.get("decision_id") or payload.get("decision_id"):
        decision_id = str(path.get("decision_id") or payload.get("decision_id"))
        decision = persistence.get_decision_record(decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="decision record not found")
        persisted_athlete_id = str(decision.get("athlete_id") or "")
        if payload.get("athlete_id") and str(payload["athlete_id"]) != persisted_athlete_id:
            raise HTTPException(status_code=403, detail="Decision/athlete ownership mismatch")
        return persisted_athlete_id

    if path.get("evidence_id"):
        evidence = persistence.get_evidence(str(path["evidence_id"]))
        if not evidence:
            raise HTTPException(status_code=404, detail="evidence not found")
        return _resolve_subject_athlete(str(evidence.get("subject_type") or ""),
                                        str(evidence.get("subject_id") or ""))

    if payload.get("subject_id") and payload.get("subject_type"):
        return _resolve_subject_athlete(str(payload["subject_type"]), str(payload["subject_id"]))

    if path.get("entity_id") or payload.get("entity_id"):
        entity_id = str(path.get("entity_id") or payload.get("entity_id"))
        athlete = persistence.get_athlete(entity_id)
        if athlete:
            return entity_id
        twin = persistence.get_digital_twin(entity_id)
        twin_state = _as_dict(twin.get("state")) if twin else {}
        if twin_state.get("athlete_id"):
            return str(twin_state["athlete_id"])
        # Never accept a body-supplied state.athlete_id as proof that an
        # entity belongs to that athlete: it would let a caller authorize one
        # athlete and write/read a different arbitrary Digital Twin entity.
        raise HTTPException(status_code=403, detail="Digital Twin entity has no persisted athlete ownership")

    query_athlete_id = request.query_params.get("athlete_id")
    if query_athlete_id:
        return query_athlete_id
    query_subject_id = request.query_params.get("subject_id")
    if query_subject_id:
        try:
            return _resolve_subject_athlete("auto", query_subject_id)
        except HTTPException:
            raise

    if payload.get("athlete_id"):
        return str(payload["athlete_id"])

    raise HTTPException(status_code=403, detail="Persisted athlete ownership could not be resolved")


def _resolve_subject_athlete(subject_type: str, subject_id: str) -> str:
    normalized = subject_type.strip().lower()
    if not subject_id.strip():
        raise HTTPException(status_code=403, detail="Evidence subject ownership is incomplete")
    if normalized in {"athlete", "player"} or persistence.get_athlete(subject_id):
        if persistence.get_athlete(subject_id):
            return subject_id
    if normalized in {"assessment", "assessment_record"} or persistence.get_assessment(subject_id):
        assessment = persistence.get_assessment(subject_id)
        if assessment:
            return str(assessment.get("athlete_id") or "")
    if normalized in {"problem", "problem_statement", "problem-statement"} or persistence.get_problem_statement(subject_id):
        problem = persistence.get_problem_statement(subject_id)
        if problem:
            return str(problem.get("athlete_id") or "")
    if normalized in {"decision", "decision_record"} or persistence.get_decision_record(subject_id):
        decision = persistence.get_decision_record(subject_id)
        if decision:
            return str(decision.get("athlete_id") or "")
    raise HTTPException(status_code=403, detail="Evidence subject has no resolvable athlete ownership")


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
            allowed_roles=(principal.role,),
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



def require_phase4_tenant_member(request: Request) -> dict[str, Any]:
    """Authorize onboarding under an existing verified tenant membership."""
    principal = require_phase4_principal(request.headers.get("authorization"))
    if principal.role not in {"coach", "academy"}:
        raise HTTPException(status_code=403, detail="Role is not authorized for academy onboarding")
    if not persistence.is_postgres_enabled():
        raise HTTPException(status_code=503, detail="Durable Phase 4 authorization requires PostgreSQL")
    route = request.scope.get("route")
    route_template = getattr(route, "path", request.url.path)
    action = f"{request.method.upper()}:{route_template}"
    allowed = False
    reason = "membership_missing_or_inactive"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM kaizo_tenant_memberships
                   WHERE tenant_id=%s AND subject_id=%s AND role=%s
                     AND status='ACTIVE' LIMIT 1""",
                (principal.tenant_id, principal.actor_id, principal.role),
            )
            allowed = cur.fetchone() is not None
            reason = "active_tenant_membership" if allowed else "membership_missing_or_inactive"
            cur.execute(
                """INSERT INTO kaizo_p14_audit_events
                   (actor_subject_id,event_type,tenant_id,resource_type,action,
                    allowed,reason_code,trace_id,metadata)
                   VALUES (%s,'authorization_decision',%s,'athlete',%s,%s,%s,%s,%s::jsonb)""",
                (
                    principal.actor_id, principal.tenant_id, action, allowed, reason,
                    request.headers.get("x-trace-id") or request.headers.get("x-request-id"),
                    '{"source":"phase4_route_guard","operation":"tenant_onboarding"}',
                ),
            )
    if not allowed:
        raise HTTPException(status_code=403, detail={"decision": "DENY", "reason_code": reason})
    return {"principal": principal, "tenant_id": principal.tenant_id}
