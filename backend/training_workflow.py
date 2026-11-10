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
from productization import coach_roster
from productization.product_api import verified_coach_scope

router = APIRouter(prefix="/api/v1/training-workflow", tags=["training-workflow"])

_MEMORY_RECORDS: list[dict[str, Any]] = []
_MEMORY_AUDIT: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_authority(value: bool) -> None:
    if not value:
        raise HTTPException(status_code=400, detail="coach_final_authority is required")


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
        # above unless durable PostgreSQL is active. Production OIDC is refused
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
    response: Dict[str, Any]
    kpi_values: Dict[str, Any]
    coach_final_authority: bool = True


class RetestRequest(BaseModel):
    athlete_id: str
    session_id: str
    baseline_reference: str
    retest_values: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class ComparisonRequest(BaseModel):
    athlete_id: str
    baseline: Dict[str, Any]
    current: Dict[str, Any]
    comparison_method: str
    coach_final_authority: bool = True


class ProgressRequest(BaseModel):
    athlete_id: str
    state: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


class NextDecisionRequest(BaseModel):
    athlete_id: str
    session_id: str
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
    _require_authority(req.coach_final_authority)
    if not req.rationale.strip() or not req.drill_id.strip():
        raise HTTPException(400, "drill_id and rationale are required")
    return _save("FEAT-033", req.athlete_id, req.model_dump(), principal, req.decision_id)


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
    _require_authority(req.coach_final_authority)
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
    _require_authority(req.coach_final_authority)
    if any(not item.strip() for item in req.cues + req.checklist):
        raise HTTPException(400, "cues and checklist items must be non-empty")
    return _save("FEAT-035", req.athlete_id, req.model_dump(), principal, session_id=req.session_id)


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
    _require_authority(req.coach_final_authority)
    if not req.response or not req.kpi_values:
        raise HTTPException(400, "response and kpi_values are required")
    return _save("FEAT-036", req.athlete_id, req.model_dump(), principal, session_id=req.session_id)


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
    _require_authority(req.coach_final_authority)
    if not req.baseline_reference.strip() or not req.retest_values:
        raise HTTPException(400, "baseline_reference and retest_values are required")
    return _save("FEAT-037", req.athlete_id, req.model_dump(), principal, session_id=req.session_id)


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
    _require_authority(req.coach_final_authority)
    if not req.baseline or not req.current or not req.comparison_method.strip():
        raise HTTPException(400, "baseline, current and comparison_method are required")
    return _save("FEAT-038", req.athlete_id, req.model_dump(), principal)


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
    _require_authority(req.coach_final_authority)
    if not req.state:
        raise HTTPException(400, "state is required")
    return _save("FEAT-039", req.athlete_id, req.model_dump(), principal)


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
    _require_authority(req.coach_final_authority)
    if not req.trigger_type.strip() or not req.trigger_reason.strip():
        raise HTTPException(400, "trigger_type and trigger_reason are required")
    return _save("FEAT-040", req.athlete_id, req.model_dump(), principal, session_id=req.session_id)


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
