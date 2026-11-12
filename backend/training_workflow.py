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
from productization import (coach_roster, coach_progression_workflow, coach_decision_workflow,
                            coach_training_workflow, coach_assessment_workflow)
from productization.product_api import verified_coach_scope

router = APIRouter(prefix="/api/v1/training-workflow", tags=["training-workflow"])

_MEMORY_RECORDS: list[dict[str, Any]] = []
_MEMORY_AUDIT: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()



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
    expected_session_decision_id: Optional[str] = None,
    baseline_reference: Optional[str] = None,
    expected_assessment_id: Optional[str] = None,
    expected_kpi_keys: Optional[set[str]] = None,
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
                if session_id and expected_session_decision_id:
                    _validate_session_parent(cur, athlete_id, session_id,
                                             expected_session_decision_id, principal)
                if baseline_reference:
                    if not expected_assessment_id:
                        raise HTTPException(status_code=409, detail="baseline assessment lineage is missing")
                    baseline_values = _load_baseline_snapshot(
                        cur, athlete_id, principal, baseline_reference, expected_assessment_id
                    )
                    if expected_kpi_keys is not None and set(baseline_values) != set(expected_kpi_keys):
                        raise HTTPException(status_code=409, detail="workflow KPI identities must exactly match the referenced baseline snapshot")
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
        if session_id and expected_session_decision_id:
            _validate_session_parent(None, athlete_id, session_id,
                                     expected_session_decision_id, principal)
        if baseline_reference:
            if not expected_assessment_id:
                raise HTTPException(status_code=409, detail="baseline assessment lineage is missing")
            baseline_values = _load_baseline_snapshot(
                None, athlete_id, principal, baseline_reference, expected_assessment_id
            )
            if expected_kpi_keys is not None and set(baseline_values) != set(expected_kpi_keys):
                raise HTTPException(status_code=409, detail="workflow KPI identities must exactly match the referenced baseline snapshot")
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


def _audit_event_matches(events, principal, action: str, expected: Dict[str, Any]) -> bool:
    for event in events:
        value = event.get("new_value") or {}
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (TypeError, ValueError):
                continue
        if (
            event.get("action") == action
            and event.get("who") == principal.actor_id
            and event.get("tenant_id") == principal.tenant_id
            and isinstance(value, dict)
            and all(value.get(key) == expected_value for key, expected_value in expected.items())
        ):
            return True
    return False


def _validate_session_parent(cur, athlete_id: str, session_id: str,
                             decision_id: str, principal: Any) -> None:
    """Require an audited FEAT-027 session under the same decision and owner."""
    if persistence.is_postgres_enabled():
        if cur is None:
            with persistence.connection() as conn:
                with conn.cursor() as read_cur:
                    return _validate_session_parent(
                        read_cur, athlete_id, session_id, decision_id, principal
                    )
        cur.execute(
            """SELECT s.plan_id
               FROM kaizo_training_sessions s
               JOIN kaizo_training_plans p
                 ON p.plan_id=s.plan_id AND p.athlete_id=s.athlete_id
               JOIN kaizo_decision_records d
                 ON d.decision_id=p.decision_id AND d.athlete_id=p.athlete_id
               JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=s.athlete_id
               WHERE s.session_id=%s AND s.athlete_id=%s
                 AND p.decision_id=%s AND d.coach_id=%s AND d.status='RECORDED'
                 AND o.tenant_id=%s AND o.coach_actor_id=%s
               FOR SHARE OF s,p,d""",
            (session_id, athlete_id, decision_id, principal.actor_id,
             principal.tenant_id, principal.actor_id),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=409,
                detail="session_id must reference an audited session under this athlete's linked decision and Coach scope",
            )
        plan_id = row[0]
        cur.execute(
            """SELECT 1 FROM kaizo_audit_logs
               WHERE tenant_id=%s AND who=%s
                 AND action='COACH_TRAINING_PLAN_CREATED'
                 AND new_value->>'plan_id'=%s
                 AND new_value->>'decision_id'=%s
                 AND new_value->>'athlete_id'=%s""",
            (principal.tenant_id, principal.actor_id, plan_id, decision_id, athlete_id),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=409, detail="training plan lacks its authoritative tenant audit event")
        cur.execute(
            """SELECT 1 FROM kaizo_audit_logs
               WHERE tenant_id=%s AND who=%s
                 AND action='COACH_TRAINING_SESSION_CREATED'
                 AND new_value->>'session_id'=%s
                 AND new_value->>'plan_id'=%s
                 AND new_value->>'athlete_id'=%s""",
            (principal.tenant_id, principal.actor_id, session_id, plan_id, athlete_id),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=409, detail="training session lacks its authoritative tenant audit event")
        return

    session = coach_training_workflow._MEMORY_SESSIONS.get(session_id)
    if not session or session.get("athlete_id") != athlete_id:
        raise HTTPException(status_code=409, detail="session_id is not a persisted session for this athlete")
    plan_id = session.get("plan_id")
    plan = coach_training_workflow._MEMORY_PLANS.get(plan_id)
    if (
        not plan or plan.get("athlete_id") != athlete_id
        or plan.get("decision_id") != decision_id
        or plan.get("created_by") != principal.actor_id
        or session.get("created_by") != principal.actor_id
    ):
        raise HTTPException(status_code=409, detail="session is not linked to this Coach-owned decision and athlete")
    events = coach_training_workflow._MEMORY_AUDIT
    if not _audit_event_matches(events, principal, "COACH_TRAINING_PLAN_CREATED", {
        "plan_id": plan_id, "decision_id": decision_id, "athlete_id": athlete_id,
    }):
        raise HTTPException(status_code=409, detail="training plan lacks its authoritative tenant audit event")
    if not _audit_event_matches(events, principal, "COACH_TRAINING_SESSION_CREATED", {
        "session_id": session_id, "plan_id": plan_id, "athlete_id": athlete_id,
    }):
        raise HTTPException(status_code=409, detail="training session lacks its authoritative tenant audit event")


def _load_baseline_snapshot(cur, athlete_id: str, principal: Any,
                            snapshot_id: str, expected_assessment_id: str) -> Dict[str, Any]:
    """Load a Coach-authored FEAT-015 baseline and return KPI-ID/value pairs."""
    if persistence.is_postgres_enabled():
        if cur is None:
            with persistence.connection() as conn:
                with conn.cursor() as read_cur:
                    return _load_baseline_snapshot(
                        read_cur, athlete_id, principal, snapshot_id, expected_assessment_id
                    )
        cur.execute(
            """SELECT s.assessment_id,s.snapshot_type,s.kpis,s.captured_by
               FROM kaizo_state_snapshots s
               JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=s.athlete_id
               WHERE s.snapshot_id=%s AND s.athlete_id=%s
                 AND o.tenant_id=%s AND o.coach_actor_id=%s
               FOR SHARE OF s""",
            (snapshot_id, athlete_id, principal.tenant_id, principal.actor_id),
        )
        row = cur.fetchone()
        if (
            row is None or row[0] != expected_assessment_id
            or row[1] != "baseline" or row[3] != principal.actor_id
        ):
            raise HTTPException(
                status_code=409,
                detail="baseline_reference must be a Coach-authored FEAT-015 baseline for this decision assessment and athlete",
            )
        cur.execute(
            """SELECT 1 FROM kaizo_audit_logs
               WHERE tenant_id=%s AND who=%s
                 AND action='COACH_STATE_SNAPSHOT_CREATED'
                 AND new_value->>'snapshot_id'=%s
                 AND new_value->>'athlete_id'=%s
                 AND new_value->>'assessment_id'=%s
                 AND new_value->>'snapshot_type'='baseline'""",
            (principal.tenant_id, principal.actor_id, snapshot_id,
             athlete_id, expected_assessment_id),
        )
        if cur.fetchone() is None:
            raise HTTPException(status_code=409, detail="baseline snapshot lacks its authoritative tenant audit event")
        kpis = row[2]
    else:
        snapshot = coach_assessment_workflow._MEMORY_SNAPSHOTS.get(snapshot_id)
        if (
            not snapshot or snapshot.get("athlete_id") != athlete_id
            or snapshot.get("assessment_id") != expected_assessment_id
            or snapshot.get("snapshot_type") != "baseline"
            or snapshot.get("captured_by") != principal.actor_id
        ):
            raise HTTPException(
                status_code=409,
                detail="baseline_reference must be a Coach-authored FEAT-015 baseline for this decision assessment and athlete",
            )
        if not _audit_event_matches(coach_assessment_workflow._MEMORY_AUDIT, principal,
                                    "COACH_STATE_SNAPSHOT_CREATED", {
            "snapshot_id": snapshot_id, "athlete_id": athlete_id,
            "assessment_id": expected_assessment_id, "snapshot_type": "baseline",
        }):
            raise HTTPException(status_code=409, detail="baseline snapshot lacks its authoritative tenant audit event")
        kpis = snapshot.get("kpis")

    if isinstance(kpis, str):
        try:
            kpis = json.loads(kpis)
        except (TypeError, ValueError):
            kpis = None
    if not isinstance(kpis, list) or not kpis:
        raise HTTPException(status_code=409, detail="baseline snapshot has no persisted KPI identity/value records")
    values: Dict[str, Any] = {}
    for item in kpis:
        if not isinstance(item, dict):
            raise HTTPException(status_code=409, detail="baseline snapshot contains an invalid KPI record")
        kpi_id = str(item.get("kpi_id") or "").strip()
        if not kpi_id or kpi_id in values or "value" not in item:
            raise HTTPException(status_code=409, detail="baseline snapshot contains duplicate or incomplete KPI identities")
        values[kpi_id] = item["value"]
    return values


def _feat033_assessment_id(athlete_id: str, decision_id: str, principal: Any) -> str:
    source = _prior_record(
        "FEAT-033", athlete_id, principal,
        lambda record, payload: record.get("decision_id") == decision_id,
    )
    payload = source.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    assessment_id = str(payload.get("assessment_id") or "").strip()
    if not assessment_id:
        raise HTTPException(status_code=409, detail="FEAT-033 lacks authoritative assessment lineage for KPI baseline validation")
    return assessment_id



def _validate_initial_decision_drill(req: "DecisionDrillRequest", principal: Any) -> Dict[str, Any]:
    """Resolve FEAT-033 inputs against authoritative Coach-owned source records."""
    if persistence.is_postgres_enabled():
        decision = persistence.get_decision_record(req.decision_id)
    else:
        import sys
        core = sys.modules.get("main")
        decision = getattr(core, "DECISION_RECORDS", {}).get(req.decision_id) if core else None
    if not decision or decision.get("athlete_id") != req.athlete_id:
        raise HTTPException(status_code=409, detail="decision_id is not a recorded decision for this athlete")
    if decision.get("coach_id") != principal.actor_id or decision.get("status") != "RECORDED":
        raise HTTPException(status_code=409, detail="decision_id is not an authoritative recorded decision by this Coach")
    # Accept only records emitted by the protected FEAT-021..025 workflow.
    # Legacy Core decision endpoints use a different audit action and are not
    # sufficient proof of verified Coach authorship.
    if persistence.is_postgres_enabled():
        source_audit = persistence.list_tenant_audit_logs(tenant_id=principal.tenant_id)
    else:
        source_audit = coach_decision_workflow._MEMORY_AUDIT
    trusted_source = any(
        item.get("action") == "COACH_DECISION_RECORD_RECORDED"
        and item.get("who") == principal.actor_id
        and item.get("tenant_id") == principal.tenant_id
        and isinstance(item.get("new_value"), dict)
        and item["new_value"].get("decision_id") == req.decision_id
        and item["new_value"].get("athlete_id") == req.athlete_id
        for item in source_audit
    )
    if not trusted_source:
        raise HTTPException(status_code=409, detail="decision_id lacks the protected Coach decision audit event for this verified scope")
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


class DrillPrescriptionRequest(BaseModel):
    athlete_id: str
    decision_id: str
    session_id: str
    drill_id: str
    objective: str
    dosage: Dict[str, Any]
    constraints: List[str] = Field(default_factory=list)


class ExecutionCueRequest(BaseModel):
    athlete_id: str
    session_id: str
    drill_id: str
    cues: List[str] = Field(min_length=1)
    checklist: List[str] = Field(min_length=1)


class ResponseRequest(BaseModel):
    athlete_id: str
    session_id: str
    drill_id: str
    prescription_record_id: str
    execution_cue_record_id: str
    response: Dict[str, Any]
    kpi_values: Dict[str, Any]


class RetestRequest(BaseModel):
    athlete_id: str
    session_id: str
    response_record_id: str
    baseline_reference: str
    retest_values: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)


class ComparisonRequest(BaseModel):
    athlete_id: str
    response_record_id: str
    retest_record_id: str
    baseline_reference: str
    baseline: Dict[str, Any]
    current: Dict[str, Any]
    comparison_method: str


class ProgressRequest(BaseModel):
    athlete_id: str
    comparison_record_id: str
    state: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)


class NextDecisionRequest(BaseModel):
    athlete_id: str
    session_id: str
    progress_record_id: str
    trigger_type: str
    trigger_reason: str
    required_evidence: List[str] = Field(min_length=1)


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
    if not req.rationale.strip() or not req.drill_id.strip():
        raise HTTPException(400, "drill_id and rationale are required")
    sources = _validate_initial_decision_drill(req, principal)
    payload = req.model_dump()
    payload["assessment_id"] = str(sources["decision"].get("assessment_id") or "")
    if not payload["assessment_id"]:
        raise HTTPException(status_code=409, detail="recorded decision has no authoritative assessment_id")
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
    predecessor = _prior_record("FEAT-033", req.athlete_id, principal,
        lambda r, p: r.get("decision_id") == req.decision_id and p.get("drill_id") == req.drill_id)
    d = req.dosage
    if not d or any(k not in d for k in ("sets", "reps")):
        raise HTTPException(400, "dosage requires sets and reps")
    if not isinstance(d["sets"], int) or d["sets"] <= 0 or not isinstance(d["reps"], int) or d["reps"] <= 0:
        raise HTTPException(400, "sets and reps must be positive integers")
    return _save("FEAT-034", req.athlete_id, req.model_dump(), principal,
                 req.decision_id, req.session_id,
                 expected_session_decision_id=req.decision_id)


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
    if any(not item.strip() for item in req.cues + req.checklist):
        raise HTTPException(400, "cues and checklist items must be non-empty")
    predecessor = _prior_record("FEAT-034", req.athlete_id, principal,
        lambda r, p: r.get("session_id") == req.session_id and p.get("drill_id") == req.drill_id)
    return _save("FEAT-035", req.athlete_id, req.model_dump(), principal,
        decision_id=predecessor.get("decision_id"), session_id=req.session_id,
        expected_session_decision_id=predecessor.get("decision_id"))


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
    if not req.response or not req.kpi_values:
        raise HTTPException(400, "response and kpi_values are required")
    prescription = _prior_record("FEAT-034", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == req.prescription_record_id and r.get("session_id") == req.session_id and p.get("drill_id") == req.drill_id)
    cues = _prior_record("FEAT-035", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == req.execution_cue_record_id and r.get("session_id") == req.session_id and p.get("drill_id") == req.drill_id)
    if cues.get("decision_id") != prescription.get("decision_id"):
        raise HTTPException(409, detail="prescription and execution cues do not share the same decision lineage")
    return _save("FEAT-036", req.athlete_id, req.model_dump(), principal,
        decision_id=prescription.get("decision_id"), session_id=req.session_id,
        expected_session_decision_id=prescription.get("decision_id"))


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
    if not req.baseline_reference.strip() or not req.retest_values:
        raise HTTPException(400, "baseline_reference and retest_values are required")
    response_record = _prior_record("FEAT-036", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == req.response_record_id and r.get("session_id") == req.session_id)
    response_payload = response_record.get("payload") or {}
    if isinstance(response_payload, str):
        response_payload = json.loads(response_payload)
    assessment_id = _feat033_assessment_id(
        req.athlete_id, response_record.get("decision_id"), principal
    )
    baseline_values = _load_baseline_snapshot(
        None, req.athlete_id, principal, req.baseline_reference, assessment_id
    )
    response_values = response_payload.get("kpi_values", {})
    if (
        not isinstance(response_values, dict)
        or set(response_values) != set(baseline_values)
        or set(req.retest_values) != set(baseline_values)
    ):
        raise HTTPException(
            status_code=409,
            detail="training response and retest KPI IDs must exactly match the linked FEAT-015 baseline KPI IDs",
        )
    return _save(
        "FEAT-037", req.athlete_id, req.model_dump(), principal,
        decision_id=response_record.get("decision_id"), session_id=req.session_id,
        expected_session_decision_id=response_record.get("decision_id"),
        baseline_reference=req.baseline_reference,
        expected_assessment_id=assessment_id,
        expected_kpi_keys=set(req.retest_values),
    )

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
    if not req.baseline or not req.current or not req.comparison_method.strip():
        raise HTTPException(400, "baseline, current and comparison_method are required")
    response_record = _prior_record(
        "FEAT-036", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == req.response_record_id,
    )
    retest_record = _prior_record(
        "FEAT-037", req.athlete_id, principal,
        lambda r, p: r.get("record_id") == req.retest_record_id
        and r.get("session_id") == response_record.get("session_id"),
    )
    retest_payload = retest_record.get("payload") or {}
    if isinstance(retest_payload, str):
        retest_payload = json.loads(retest_payload)
    if retest_record.get("decision_id") != response_record.get("decision_id"):
        raise HTTPException(status_code=409, detail="response and retest do not share the same decision lineage")
    if retest_payload.get("baseline_reference") != req.baseline_reference:
        raise HTTPException(status_code=409, detail="comparison baseline_reference must match the linked retest baseline")
    assessment_id = _feat033_assessment_id(
        req.athlete_id, response_record.get("decision_id"), principal
    )
    baseline_values = _load_baseline_snapshot(
        None, req.athlete_id, principal, req.baseline_reference, assessment_id
    )
    if req.baseline != baseline_values or req.current != retest_payload.get("retest_values"):
        raise HTTPException(
            status_code=409,
            detail="comparison baseline/current must equal the referenced FEAT-015 baseline and linked retest KPI values",
        )
    if not _same_keys(req.baseline, req.current):
        raise HTTPException(status_code=409, detail="comparison KPI keys must match exactly")
    return _save(
        "FEAT-038", req.athlete_id, req.model_dump(), principal,
        decision_id=response_record.get("decision_id"), session_id=response_record.get("session_id"),
        expected_session_decision_id=response_record.get("decision_id"),
        baseline_reference=req.baseline_reference,
        expected_assessment_id=assessment_id,
        expected_kpi_keys=set(req.baseline),
    )

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
    if not req.state:
        raise HTTPException(400, "state is required")
    comparison = _prior_record("FEAT-038", req.athlete_id, principal, lambda r, p: r.get("record_id") == req.comparison_record_id)
    return _save("FEAT-039", req.athlete_id, req.model_dump(), principal,
        decision_id=comparison.get("decision_id"), session_id=comparison.get("session_id"),
        expected_session_decision_id=comparison.get("decision_id"))


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
    if not req.trigger_type.strip() or not req.trigger_reason.strip():
        raise HTTPException(400, "trigger_type and trigger_reason are required")
    progress = _prior_record("FEAT-039", req.athlete_id, principal, lambda r, p: r.get("record_id") == req.progress_record_id)
    if progress.get("session_id") != req.session_id:
        raise HTTPException(409, detail="next-decision trigger session does not match the linked progress record")
    return _save("FEAT-040", req.athlete_id, req.model_dump(), principal,
        decision_id=progress.get("decision_id"), session_id=req.session_id,
        expected_session_decision_id=progress.get("decision_id"))


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
