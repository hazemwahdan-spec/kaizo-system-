"""End-to-end training decision-cycle workflow for FEAT-033..040.

This module adds feature-specific semantics on top of the durable persistence
boundary. It never authorizes autonomous execution: Coach Final Authority is
mandatory and execution_authorized is always False.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

import persistence

router = APIRouter(prefix="/api/v1/training-workflow", tags=["training-workflow"])


def _now() -> str:
    return datetime.utcnow().isoformat()


def _require_authority(value: bool) -> None:
    if not value:
        raise HTTPException(status_code=400, detail="coach_final_authority is required")


def _ensure_schema() -> None:
    if not persistence.is_postgres_enabled():
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS kaizo_training_workflow_records (
                record_id TEXT PRIMARY KEY,
                feature_id TEXT NOT NULL,
                athlete_id TEXT NOT NULL,
                decision_id TEXT,
                session_id TEXT,
                payload JSONB NOT NULL,
                created_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                coach_final_authority BOOLEAN NOT NULL,
                execution_authorized BOOLEAN NOT NULL DEFAULT FALSE
            );
            CREATE INDEX IF NOT EXISTS idx_kaizo_training_workflow_feature
                ON kaizo_training_workflow_records(feature_id, athlete_id, created_at);
            """)
        conn.commit()


def _save(feature_id: str, athlete_id: str, payload: Dict[str, Any],
          created_by: str, decision_id: Optional[str] = None,
          session_id: Optional[str] = None) -> Dict[str, Any]:
    record = {
        "record_id": str(uuid4()),
        "feature_id": feature_id,
        "athlete_id": athlete_id,
        "decision_id": decision_id,
        "session_id": session_id,
        "payload": payload,
        "created_by": created_by,
        "created_at": _now(),
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO kaizo_training_workflow_records
                    (record_id,feature_id,athlete_id,decision_id,session_id,payload,
                     created_by,created_at,coach_final_authority,execution_authorized)
                    VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s)""",
                    (record["record_id"], feature_id, athlete_id, decision_id,
                     session_id, __import__("json").dumps(payload), created_by,
                     record["created_at"], True, False),
                )
            conn.commit()
        persistence.append_audit(
            timestamp=record["created_at"], who=created_by,
            action=f"{feature_id}_RECORDED", old_value=None, new_value=record,
            why="Training workflow record persisted under Coach Final Authority.",
        )
    return record


def _list(feature_id: str, athlete_id: str) -> List[Dict[str, Any]]:
    if not persistence.is_postgres_enabled():
        return []
    _ensure_schema()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT record_id,feature_id,athlete_id,decision_id,session_id,
                          payload,created_by,created_at,coach_final_authority,
                          execution_authorized
                   FROM kaizo_training_workflow_records
                   WHERE feature_id=%s AND athlete_id=%s
                   ORDER BY created_at,record_id""",
                (feature_id, athlete_id),
            )
            rows = cur.fetchall()
    return [{
        "record_id": r[0], "feature_id": r[1], "athlete_id": r[2],
        "decision_id": r[3], "session_id": r[4], "payload": r[5],
        "created_by": r[6], "created_at": r[7],
        "coach_final_authority": r[8], "execution_authorized": r[9],
    } for r in rows]


class DecisionDrillRequest(BaseModel):
    athlete_id: str
    decision_id: str
    drill_id: str
    rationale: str
    evidence_refs: List[str] = Field(min_length=1)
    selected_by: str
    coach_final_authority: bool = True


class DrillPrescriptionRequest(BaseModel):
    athlete_id: str
    decision_id: str
    session_id: str
    drill_id: str
    objective: str
    dosage: Dict[str, Any]
    constraints: List[str] = Field(default_factory=list)
    prescribed_by: str
    coach_final_authority: bool = True


class ExecutionCueRequest(BaseModel):
    athlete_id: str
    session_id: str
    drill_id: str
    cues: List[str] = Field(min_length=1)
    checklist: List[str] = Field(min_length=1)
    created_by: str
    coach_final_authority: bool = True


class ResponseRequest(BaseModel):
    athlete_id: str
    session_id: str
    response: Dict[str, Any]
    kpi_values: Dict[str, Any]
    observed_by: str
    coach_final_authority: bool = True


class RetestRequest(BaseModel):
    athlete_id: str
    session_id: str
    baseline_reference: str
    retest_values: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)
    retested_by: str
    coach_final_authority: bool = True


class ComparisonRequest(BaseModel):
    athlete_id: str
    baseline: Dict[str, Any]
    current: Dict[str, Any]
    comparison_method: str
    compared_by: str
    coach_final_authority: bool = True


class ProgressRequest(BaseModel):
    athlete_id: str
    state: Dict[str, Any]
    evidence_refs: List[str] = Field(min_length=1)
    updated_by: str
    coach_final_authority: bool = True


class NextDecisionRequest(BaseModel):
    athlete_id: str
    session_id: str
    trigger_type: str
    trigger_reason: str
    required_evidence: List[str] = Field(min_length=1)
    created_by: str
    coach_final_authority: bool = True


@router.post("/feat-033/decision-drill", status_code=status.HTTP_201_CREATED)
def select_decision_drill(req: DecisionDrillRequest):
    _require_authority(req.coach_final_authority)
    if not req.rationale.strip() or not req.drill_id.strip():
        raise HTTPException(400, "drill_id and rationale are required")
    return _save("FEAT-033", req.athlete_id, req.model_dump(),
                 req.selected_by, req.decision_id)


@router.post("/feat-034/drill-prescription", status_code=status.HTTP_201_CREATED)
def prescribe_drill(req: DrillPrescriptionRequest):
    _require_authority(req.coach_final_authority)
    d = req.dosage
    if not d or any(k not in d for k in ("sets", "reps")):
        raise HTTPException(400, "dosage requires sets and reps")
    if not isinstance(d["sets"], int) or d["sets"] <= 0 or not isinstance(d["reps"], int) or d["reps"] <= 0:
        raise HTTPException(400, "sets and reps must be positive integers")
    return _save("FEAT-034", req.athlete_id, req.model_dump(),
                 req.prescribed_by, req.decision_id, req.session_id)


@router.post("/feat-035/execution-cues", status_code=status.HTTP_201_CREATED)
def record_execution_cues(req: ExecutionCueRequest):
    _require_authority(req.coach_final_authority)
    if any(not item.strip() for item in req.cues + req.checklist):
        raise HTTPException(400, "cues and checklist items must be non-empty")
    return _save("FEAT-035", req.athlete_id, req.model_dump(),
                 req.created_by, session_id=req.session_id)


@router.post("/feat-036/training-response", status_code=status.HTTP_201_CREATED)
def capture_training_response(req: ResponseRequest):
    _require_authority(req.coach_final_authority)
    if not req.response or not req.kpi_values:
        raise HTTPException(400, "response and kpi_values are required")
    return _save("FEAT-036", req.athlete_id, req.model_dump(),
                 req.observed_by, session_id=req.session_id)


@router.post("/feat-037/retest", status_code=status.HTTP_201_CREATED)
def capture_retest(req: RetestRequest):
    _require_authority(req.coach_final_authority)
    if not req.baseline_reference.strip() or not req.retest_values:
        raise HTTPException(400, "baseline_reference and retest_values are required")
    return _save("FEAT-037", req.athlete_id, req.model_dump(),
                 req.retested_by, session_id=req.session_id)


@router.post("/feat-038/before-after", status_code=status.HTTP_201_CREATED)
def compare_before_after(req: ComparisonRequest):
    _require_authority(req.coach_final_authority)
    if not req.baseline or not req.current or not req.comparison_method.strip():
        raise HTTPException(400, "baseline, current and comparison_method are required")
    return _save("FEAT-038", req.athlete_id, req.model_dump(), req.compared_by)


@router.post("/feat-039/progress-state", status_code=status.HTTP_201_CREATED)
def update_progress_state(req: ProgressRequest):
    _require_authority(req.coach_final_authority)
    if not req.state:
        raise HTTPException(400, "state is required")
    return _save("FEAT-039", req.athlete_id, req.model_dump(), req.updated_by)


@router.post("/feat-040/next-decision-trigger", status_code=status.HTTP_201_CREATED)
def create_next_decision_trigger(req: NextDecisionRequest):
    _require_authority(req.coach_final_authority)
    if not req.trigger_type.strip() or not req.trigger_reason.strip():
        raise HTTPException(400, "trigger_type and trigger_reason are required")
    return _save("FEAT-040", req.athlete_id, req.model_dump(),
                 req.created_by, session_id=req.session_id)


@router.get("/athletes/{athlete_id}")
def get_training_workflow(athlete_id: str):
    return {
        "athlete_id": athlete_id,
        "features": {
            feature: _list(feature, athlete_id)
            for feature in (
                "FEAT-033","FEAT-034","FEAT-035","FEAT-036",
                "FEAT-037","FEAT-038","FEAT-039","FEAT-040"
            )
        },
    }
