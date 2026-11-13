"""Ownership-scoped, auditable FEAT-033..040 Coach workflow.

Every request requires a verified Coach principal (OIDC in production) and a
server-side ownership lookup. Caller-supplied actor identifiers are ignored.
Training record and tenant-scoped audit event are committed in one transaction.
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

import persistence
from productization import coach_roster, coach_progression_workflow, coach_decision_workflow, coach_assessment_workflow
from productization.product_api import verified_coach_scope

router = APIRouter(prefix="/api/v1/training-workflow", tags=["training-workflow"])

_MEMORY_RECORDS: list[dict[str, Any]] = []
_MEMORY_AUDIT: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_authority(principal: Any) -> None:
    # Caller-supplied coach_final_authority is compatibility data, never an authorization source.
    if (getattr(principal, "role", None) != "coach"
            or not getattr(principal, "actor_id", None)
            or not getattr(principal, "tenant_id", None)):
        raise HTTPException(status_code=403, detail="server-derived Coach authority is required")


def _coach_for_athlete(
    athlete_id: str,
    authorization: str | None,
    actor_id: str | None,
    role: str | None,
    tenant_id: str | None,
    owner: str | None,
):
    # verified_coach_scope uses JWT issuer/audience/JWKS validation in OIDC mode.
    # Development headers are accepted only when KAIZO_IDENTITY_MODE=development.
    principal = verified_coach_scope(authorization, actor_id, role, tenant_id, owner)
    if not persistence.is_postgres_enabled() and principal.verified:
        raise HTTPException(status_code=503, detail="durable Coach workflow requires PostgreSQL")
    athlete = coach_roster.get_owned_athlete(
        tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id,
        athlete_id=athlete_id,
    )
    if athlete is None:
        # Avoid disclosing whether an athlete exists in another Coach/tenant scope.
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return principal


def _ensure_schema() -> None:
    """Compatibility no-op; persistence.initialize() owns all feature DDL."""
    return None


def _save(
    feature_id: str,
    athlete_id: str,
    payload: Dict[str, Any],
    principal: Any,
    decision_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    record = {
        "record_id": str(uuid4()),
        "feature_id": feature_id,
        "athlete_id": athlete_id,
        "tenant_id": principal.tenant_id,
        "coach_actor_id": principal.actor_id,
        "decision_id": decision_id,
        "session_id": session_id,
        "payload": payload,
        "created_by": principal.actor_id,
        "created_at": _now(),
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    audit = {
        "timestamp": record["created_at"],
        "who": principal.actor_id,
        "action": f"{feature_id}_RECORDED",
        "old_value": None,
        "new_value": record,
        "why": "Training workflow record persisted under verified Coach ownership and Coach Final Authority.",
        "tenant_id": principal.tenant_id,
    }

    if persistence.is_postgres_enabled():
        # Schema is provisioned by persistence.initialize(); requests never run DDL.
        # Lock the authoritative ownership row in the same transaction as both
        # the workflow record and its tenant-scoped audit event. A concurrent
        # ownership removal/transfer must wait until this write commits.
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_coach_athlete_ownership
                       WHERE athlete_id=%s AND tenant_id=%s AND coach_actor_id=%s
                       FOR UPDATE""",
                    (athlete_id, principal.tenant_id, principal.actor_id),
                )
                if cur.fetchone() is None:
                    raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
                cur.execute(
                    """INSERT INTO kaizo_training_workflow_records
                    (record_id,feature_id,athlete_id,decision_id,session_id,payload,
                     created_by,created_at,coach_final_authority,execution_authorized,
                     tenant_id,coach_actor_id)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)""",
                    (
                        record["record_id"], feature_id, athlete_id, decision_id,
                        session_id, json.dumps(payload), principal.actor_id,
                        record["created_at"], True, False,
                        principal.tenant_id, principal.actor_id,
                    ),
                )
            persistence.append_tenant_audit(
                tenant_id=audit["tenant_id"],
                timestamp=audit["timestamp"],
                who=audit["who"],
                action=audit["action"],
                old_value=audit["old_value"],
                new_value=audit["new_value"],
                why=audit["why"],
            )
    else:
        # Explicitly development/test-only adapter. Production OIDC is refused
        # above unless durable PostgreSQL is active.
        _MEMORY_RECORDS.append(record)
        _MEMORY_AUDIT.append(audit)
    return record


def _list(feature_id: str, athlete_id: str, tenant_id: str, coach_actor_id: str) -> List[Dict[str, Any]]:
    if not persistence.is_postgres_enabled():
        return [
            dict(item) for item in _MEMORY_RECORDS
            if item["feature_id"] == feature_id
            and item["athlete_id"] == athlete_id
            and item["tenant_id"] == tenant_id
            and item["coach_actor_id"] == coach_actor_id
        ]
    # Read paths must never initialize or mutate schema; migrations/writes own DDL.
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT r.record_id,r.feature_id,r.athlete_id,r.decision_id,r.session_id,
                          r.payload,r.created_by,r.created_at,r.coach_final_authority,
                          r.execution_authorized,r.tenant_id,r.coach_actor_id
                   FROM kaizo_training_workflow_records r
                   JOIN kaizo_coach_athlete_ownership o
                     ON o.athlete_id=r.athlete_id
                    AND o.tenant_id=r.tenant_id
                    AND o.coach_actor_id=r.coach_actor_id
                   WHERE r.feature_id=%s AND r.athlete_id=%s
                     AND r.tenant_id=%s AND r.coach_actor_id=%s
                   ORDER BY r.created_at,r.record_id""",
                (feature_id, athlete_id, tenant_id, coach_actor_id),
            )
            rows = cur.fetchall()
    return [{
        "record_id": r[0], "feature_id": r[1], "athlete_id": r[2],
        "decision_id": r[3], "session_id": r[4], "payload": r[5],
        "created_by": r[6], "created_at": r[7],
        "coach_final_authority": r[8], "execution_authorized": r[9],
        "tenant_id": r[10], "coach_actor_id": r[11],
    } for r in rows]



def _prior_record(feature_id: str, athlete_id: str, principal: Any, predicate):
    """Return a same-owner predecessor record or fail closed."""
    for item in _list(feature_id, athlete_id, principal.tenant_id, principal.actor_id):
        payload = item.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                continue
        if predicate(item, payload):
            return item
    raise HTTPException(status_code=409, detail=f"required linked predecessor {feature_id} was not found in this Coach/athlete scope")


def _same_keys(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    return bool(left) and set(left.keys()) == set(right.keys())

def _baseline_snapshot_for_response(response_record: Dict[str, Any], baseline_reference: str,
                                     principal: Any, athlete_id: str):
    """Resolve the baseline snapshot linked to the response's authoritative decision."""
    decision_id = response_record.get("decision_id")
    decision = coach_decision_workflow.get_recorded_decision_for_scope(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id, decision_id=str(decision_id or ""),
    )
    if decision is None or not decision.get("assessment_id"):
        raise HTTPException(status_code=409, detail="response decision has no same-scope recorded assessment lineage")
    snapshot = coach_assessment_workflow.get_state_snapshot(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id, snapshot_id=baseline_reference,
    )
    if (snapshot is None or snapshot.get("snapshot_type") != "baseline"
            or snapshot.get("athlete_id") != athlete_id
            or snapshot.get("captured_by") != principal.actor_id
            or snapshot.get("assessment_id") != decision.get("assessment_id")):
        raise HTTPException(status_code=409, detail="baseline_reference must identify this Coach's baseline snapshot for the decision assessment")
    raw_kpis = snapshot.get("kpis") or []
    if isinstance(raw_kpis, str):
        try:
            raw_kpis = json.loads(raw_kpis)
        except (TypeError, ValueError):
            raw_kpis = []
    if not isinstance(raw_kpis, list):
        raise HTTPException(status_code=409, detail="linked baseline snapshot has no valid KPI identity list")
    values: Dict[str, Any] = {}
    for item in raw_kpis:
        if not isinstance(item, dict):
            raise HTTPException(status_code=409, detail="linked baseline snapshot contains an invalid KPI entry")
        kpi_id = str(item.get("kpi_id") or "").strip()
        if not kpi_id or kpi_id in values or "value" not in item:
            raise HTTPException(status_code=409, detail="linked baseline snapshot contains missing or duplicate KPI identities")
        values[kpi_id] = item["value"]
    if not values:
        raise HTTPException(status_code=409, detail="linked baseline snapshot contains no KPI values")
    return snapshot, values




def _validate_initial_decision_drill(req: "DecisionDrillRequest", principal: Any) -> Dict[str, Any]:
    """Resolve FEAT-033 inputs against authoritative Coach-owned source records."""
    decision = coach_decision_workflow.get_recorded_decision_for_scope(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=req.athlete_id, decision_id=req.decision_id,
    )
    if decision is None:
        raise HTTPException(status_code=409, detail="decision_id is not a recorded decision in this Coach/tenant/athlete scope")
    problem_id = str(decision.get("problem_id") or "").strip()
    if not problem_id:
        raise HTTPException(status_code=409, detail="recorded decision has no authoritative problem_id")
    drills = coach_progression_workflow.list_drills(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        include_drafts=False,
    )
    drill = next((item for item in drills if item.get("drill_id") == req.drill_id
                  and item.get("status") == "PUBLISHED" and item.get("coach_review") is True
                  and item.get("approved_by") == principal.actor_id), None)
    if drill is None:
        raise HTTPException(status_code=409, detail="drill_id is not a Coach-reviewed published drill in this Coach scope")
    links = coach_progression_workflow.list_problem_drill_links(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=req.athlete_id, problem_id=problem_id,
    )
    link = next((item for item in (links or []) if item.get("drill_id") == req.drill_id
                 and item.get("problem_id") == problem_id
                 and item.get("athlete_id") == req.athlete_id
                 and item.get("tenant_id") == principal.tenant_id
                 and item.get("coach_actor_id") == principal.actor_id), None)
    if link is None:
        raise HTTPException(status_code=409, detail="drill has no verified problem-drill link for this decision and athlete")
    linked_evidence = set(link.get("evidence_ids") or [])
    if not req.evidence_refs or not set(req.evidence_refs).issubset(linked_evidence):
        raise HTTPException(status_code=409, detail="FEAT-033 evidence_refs must come from the verified problem-drill link evidence")
    return {"decision": decision, "problem_id": problem_id, "drill": drill, "problem_drill_link": link}

def reset_memory_state() -> None:
    """Test helper; clears only the isolated in-memory adapter."""
    _MEMORY_RECORDS.clear()
    _MEMORY_AUDIT.clear()


class DecisionDrillRequest(BaseModel):
    athlete_id: str
    decision_id: str
    drill_id: str
    rationale: str
    evidence_refs: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class DrillPrescriptionRequest(BaseModel):
    athlete_id: str
    decision_id: str
    session_id: str
    drill_id: str
    objective: str
    dosage: Dict[str, Any]
    constraints: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class ExecutionCueRequest(BaseModel):
    athlete_id: str
    session_id: str
    drill_id: str
    cues: List[str] = Field(min_length=1)
    checklist: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class ResponseRequest(BaseModel):
    athlete_id: str
    session_id: str
    drill_id: str
    prescription_record_id: str
    execution_cue_record_id: str
    response: Dict[str, Any]
    kpi_values: Dict[str, Any]
    coach_final_authority: bool = True


class RetestRequest(BaseModel):
    athlete_id: str
    session_id: str
    response_record_id: str
    baseline_reference: str
    retest_values: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class ComparisonRequest(BaseModel):
    athlete_id: str
    response_record_id: str
    retest_record_id: str
    baseline: Dict[str, Any]
    current: Dict[str, Any]
    comparison_method: str
    coach_final_authority: bool = True


class ProgressRequest(BaseModel):
    athlete_id: str
    comparison_record_id: str
    state: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class NextDecisionRequest(BaseModel):
    athlete_id: str
    session_id: str
    progress_record_id: str
    trigger_type: str
    trigger_reason: str
    required_evidence: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


def _headers(
    authorization: str | None, actor_id: str | None, role: str | None,
    tenant_id: str | None, owner: str | None, athlete_id: str,
):
    return _coach_for_athlete(athlete_id, authorization, actor_id, role, tenant_id, owner)


@router.post("/feat-033/decision-drill", status_code=status.HTTP_201_CREATED)
def select_decision_drill(
    req: DecisionDrillRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    _require_authority(principal)
    if not req.rationale.strip() or not req.drill_id.strip():
        raise HTTPException(400, "drill_id and rationale are required")
    sources = _validate_initial_decision_drill(req, principal)
    payload = req.model_dump()
    payload["problem_id"] = sources["problem_id"]
    payload["problem_drill_link_id"] = sources["problem_drill_link"].get("link_id")
    return _save("FEAT-033", req.athlete_id, payload, principal, req.decision_id)


@router.post("/feat-034/drill-prescription", status_code=status.HTTP_201_CREATED)
def prescribe_drill(
    req: DrillPrescriptionRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    _require_authority(principal)
    predecessor = _prior_record("FEAT-033", req.athlete_id, principal,
        lambda r, p: r.get("decision_id") == req.decision_id and p.get("drill_id") == req.drill_id)
    d = req.dosage
    if not d or any(k not in d for k in ("sets", "reps")):
        raise HTTPException(400, "dosage requires sets and reps")
    if not isinstance(d["sets"], int) or d["sets"] <= 0 or not isinstance(d["reps"], int) or d["reps"] <= 0:
        raise HTTPException(400, "sets and reps must be positive integers")
    return _save("FEAT-034", req.athlete_id, req.model_dump(), principal, req.decision_id, req.session_id)


@router.post("/feat-035/execution-cues", status_code=status.HTTP_201_CREATED)
def record_execution_cues(
    req: ExecutionCueRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    _require_authority(principal)
    if any(not item.strip() for item in req.cues + req.checklist):
        raise HTTPException(400, "cues and checklist items must be non-empty")
    predecessor = _prior_record("FEAT-034", req.athlete_id, principal,
        lambda r, p: r.get("session_id") == req.session_id and p.get("drill_id") == req.drill_id)
    return _save("FEAT-035", req.athlete_id, req.model_dump(), principal,
        decision_id=predecessor.get("decision_id"), session_id=req.session_id)


@router.post("/feat-036/training-response", status_code=status.HTTP_201_CREATED)
def capture_training_response(
    req: ResponseRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    _require_authority(principal)
    if not req.response or not req.kpi_values:
        raise HTTPException(400, "response and kpi_values are required")
    prescription = _prior_record("FEAT-034", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == req.prescription_record_id and r.get("session_id") == req.session_id and p.get("drill_id") == req.drill_id)
    cues = _prior_record("FEAT-035", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == req.execution_cue_record_id and r.get("session_id") == req.session_id and p.get("drill_id") == req.drill_id)
    if cues.get("decision_id") != prescription.get("decision_id"):
        raise HTTPException(409, detail="prescription and execution cues do not share the same decision lineage")
    return _save("FEAT-036", req.athlete_id, req.model_dump(), principal, decision_id=prescription.get("decision_id"), session_id=req.session_id)


@router.post("/feat-037/retest", status_code=status.HTTP_201_CREATED)
def capture_retest(
    req: RetestRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    _require_authority(principal)
    if not req.baseline_reference.strip() or not req.retest_values:
        raise HTTPException(400, "baseline_reference and retest_values are required")
    response_record = _prior_record("FEAT-036", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == req.response_record_id and r.get("session_id") == req.session_id)
    response_payload = response_record.get("payload") or {}
    if isinstance(response_payload, str): response_payload = json.loads(response_payload)
    _, baseline_values = _baseline_snapshot_for_response(
        response_record, req.baseline_reference, principal, req.athlete_id,
    )
    response_values = response_payload.get("kpi_values") or {}
    if not _same_keys(response_values, req.retest_values):
        raise HTTPException(409, detail="retest KPI keys must exactly match the linked training response")
    if not set(response_values).issubset(set(baseline_values)):
        raise HTTPException(409, detail="response KPI identities must exist in the referenced baseline snapshot")
    return _save("FEAT-037", req.athlete_id, req.model_dump(), principal, decision_id=response_record.get("decision_id"), session_id=req.session_id)


@router.post("/feat-038/before-after", status_code=status.HTTP_201_CREATED)
def compare_before_after(
    req: ComparisonRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    _require_authority(principal)
    if not req.baseline or not req.current or not req.comparison_method.strip():
        raise HTTPException(400, "baseline, current and comparison_method are required")
    response_record = _prior_record("FEAT-036", req.athlete_id, principal, lambda r, p: r.get("record_id") == req.response_record_id)
    retest_record = _prior_record("FEAT-037", req.athlete_id, principal, lambda r, p: r.get("record_id") == req.retest_record_id and r.get("session_id") == response_record.get("session_id"))
    response_payload = response_record.get("payload") or {}
    retest_payload = retest_record.get("payload") or {}
    if isinstance(response_payload, str): response_payload = json.loads(response_payload)
    if isinstance(retest_payload, str): retest_payload = json.loads(retest_payload)
    baseline_reference = str(retest_payload.get("baseline_reference") or "")
    if not baseline_reference:
        raise HTTPException(409, detail="linked retest has no baseline snapshot reference")
    _, baseline_values = _baseline_snapshot_for_response(
        response_record, baseline_reference, principal, req.athlete_id,
    )
    response_values = response_payload.get("kpi_values") or {}
    if not set(response_values).issubset(set(baseline_values)):
        raise HTTPException(409, detail="response KPI identities are not present in the referenced baseline snapshot")
    expected_baseline = {key: baseline_values[key] for key in response_values}
    if req.baseline != expected_baseline or req.current != retest_payload.get("retest_values"):
        raise HTTPException(409, detail="comparison must use the referenced baseline snapshot values and linked retest values")
    if not _same_keys(req.baseline, req.current):
        raise HTTPException(409, detail="comparison KPI keys must match exactly")
    if retest_record.get("decision_id") != response_record.get("decision_id"):
        raise HTTPException(409, detail="response and retest do not share the same decision lineage")
    return _save("FEAT-038", req.athlete_id, req.model_dump(), principal, decision_id=response_record.get("decision_id"), session_id=response_record.get("session_id"))


@router.post("/feat-039/progress-state", status_code=status.HTTP_201_CREATED)
def update_progress_state(
    req: ProgressRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    _require_authority(principal)
    if not req.state:
        raise HTTPException(400, "state is required")
    comparison = _prior_record("FEAT-038", req.athlete_id, principal, lambda r, p: r.get("record_id") == req.comparison_record_id)
    return _save("FEAT-039", req.athlete_id, req.model_dump(), principal,
        decision_id=comparison.get("decision_id"), session_id=comparison.get("session_id"))


@router.post("/feat-040/next-decision-trigger", status_code=status.HTTP_201_CREATED)
def create_next_decision_trigger(
    req: NextDecisionRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, req.athlete_id)
    _require_authority(principal)
    if not req.trigger_type.strip() or not req.trigger_reason.strip():
        raise HTTPException(400, "trigger_type and trigger_reason are required")
    progress = _prior_record("FEAT-039", req.athlete_id, principal, lambda r, p: r.get("record_id") == req.progress_record_id)
    if progress.get("session_id") != req.session_id:
        raise HTTPException(409, detail="next-decision trigger session does not match the linked progress record")
    progress_payload = progress.get("payload") or {}
    if isinstance(progress_payload, str):
        try:
            progress_payload = json.loads(progress_payload)
        except (TypeError, ValueError):
            raise HTTPException(409, detail="linked progress record has invalid comparison lineage")
    comparison_id = str(progress_payload.get("comparison_record_id") or "").strip() if isinstance(progress_payload, dict) else ""
    if not comparison_id:
        raise HTTPException(409, detail="linked progress record has no comparison evidence")
    _prior_record(
        "FEAT-038", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == comparison_id
        and r.get("decision_id") == progress.get("decision_id")
        and r.get("session_id") == req.session_id,
    )
    if comparison_id not in req.required_evidence:
        raise HTTPException(409, detail="required_evidence must include the linked FEAT-038 comparison record")
    return _save("FEAT-040", req.athlete_id, req.model_dump(), principal,
        decision_id=progress.get("decision_id"), session_id=req.session_id)


@router.get("/athletes/{athlete_id}")
def get_training_workflow(
    athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _headers(authorization, actor_id, role, tenant_id, owner, athlete_id)
    return {
        "athlete_id": athlete_id,
        "features": {
            feature: _list(feature, athlete_id, principal.tenant_id, principal.actor_id)
            for feature in (
                "FEAT-033", "FEAT-034", "FEAT-035", "FEAT-036",
                "FEAT-037", "FEAT-038", "FEAT-039", "FEAT-040",
            )
        },
        "coach_final_authority": True,
        "execution_authorized": False,
    }
