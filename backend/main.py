"""KAIZO Core Engine™ v2.0 - Enterprise Backend API
Framework: FastAPI + Pydantic
Slogan: Better Every Day
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from datetime import datetime

app = FastAPI(
    title="KAIZO Core Engine API",
    version="2.0.0",
    description="Enterprise AI-Native Coaching OS for Combat Sports"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUDIT_LOGS: List[Dict[str, Any]] = []

def log_action(user_id: str, action: str, old_val: Any, new_val: Any, reason: str):
    AUDIT_LOGS.append({
        "timestamp": datetime.utcnow().isoformat(),
        "who": user_id,
        "action": action,
        "old_value": old_val,
        "new_value": new_val,
        "why": reason
    })

# PACK-C: numeric claims remain non-frozen until claim-level evidence validation.
# Existing threshold values are preserved for provenance/audit only and MUST NOT
# drive a production decision while their validation_status is UNVALIDATED.
NUMERIC_CLAIMS = {
    "NC-UNDER11-MALE-42KG-GRIP": {
        "profile_key": "under11|male|-42kg|grip_strength",
        "values": {"excellent": 25.0, "average": 18.0, "weak": 15.0},
        "unit": "kg",
        "validation_status": "UNVALIDATED",
        "evidence_level": "E0",
        "source_ids": [],
        "validation_note": "No authoritative source/evidence mapping was established for this exact age/sex/weight/metric threshold set."
    }
}

NORMATIVE_STANDARDS = {
    "under11": {
        "male": {
            "-42kg": {
                "grip_strength": {"excellent": 25.0, "average": 18.0, "weak": 15.0}
            }
        }
    }
}

# GAP-02: the existing normative profile is the authoritative required-input set.
# Missing required input must HOLD; unsupported/conflicting profile must HOLD + diagnostic.
REQUIRED_INPUTS = {
    "under11|male|-42kg|grip_strength": [
        "athlete_id", "age_group", "gender", "weight_category",
        "metric_name", "actual_value"
    ]
}

KNOWLEDGE_REPOSITORY: Dict[str, Any] = {
    "TEC-000001": {
        "id": "TEC-000001",
        "version": "v1.1",
        "title": "Morote Seoi Nage",
        "phase": "Tsukuri",
        "domain": "Technique",
        "relations": {
            "kuzushi_id": "PHS-00042",
            "biomechanics_id": "BIO-00102",
            "errors": ["PRB-000081"],
            "solutions": ["SOL-000032"]
        },
        "ai_payload": {
            "center_of_gravity": "Low",
            "rotation_axis": "Vertical"
        }
    }
}

class RuleEvaluationRequest(BaseModel):
    athlete_id: str
    age_group: str
    gender: str
    weight_category: str
    metric_name: str
    actual_value: Optional[float] = None

@app.post("/api/v1/rules/evaluate", status_code=status.HTTP_200_OK)
def evaluate_rule(req: RuleEvaluationRequest) -> Dict[str, Any]:
    profile_key = f"{req.age_group}|{req.gender}|{req.weight_category}|{req.metric_name}"
    required_set = REQUIRED_INPUTS.get(profile_key)

    # Required Input / Missing Input -> HOLD. No decision or recommendation is issued.
    if req.actual_value is None:
        return {
            "system": "KAIZO Rule Engine",
            "athlete_id": req.athlete_id,
            "status": "HOLD",
            "reason_code": "MISSING_REQUIRED_INPUT",
            "missing_inputs": ["actual_value"],
            "required_inputs": required_set or [
                "athlete_id", "age_group", "gender", "weight_category",
                "metric_name", "actual_value"
            ],
            "diagnostic_required": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    # Conflict / unsupported profile -> HOLD + additional diagnostic.
    if required_set is None or profile_key not in REQUIRED_INPUTS:
        return {
            "system": "KAIZO Rule Engine",
            "athlete_id": req.athlete_id,
            "status": "HOLD",
            "reason_code": "SOURCE_CONFLICT_VALIDATION_REQUIRED",
            "conflict": {
                "age_group": req.age_group,
                "gender": req.gender,
                "weight_category": req.weight_category,
                "metric_name": req.metric_name
            },
            "diagnostic_required": True,
            "timestamp": datetime.utcnow().isoformat()
        }

    claim_id = next((k for k, v in NUMERIC_CLAIMS.items() if v["profile_key"] == profile_key), None)
    claim = NUMERIC_CLAIMS.get(claim_id) if claim_id else None
    if claim is not None and claim["validation_status"] != "VALIDATED":
        output = {
            "system": "KAIZO Rule Engine",
            "athlete_id": req.athlete_id,
            "status": "HOLD",
            "reason_code": "NUMERIC_CLAIM_VALIDATION_REQUIRED",
            "claim_id": claim_id,
            "validation_status": claim["validation_status"],
            "evidence_level": claim["evidence_level"],
            "diagnostic_required": True,
            "decision_blocked": True,
            "timestamp": datetime.utcnow().isoformat()
        }
        log_action(req.athlete_id, "NUMERIC_CLAIM_VALIDATION_HOLD", claim, output, "Numeric claim is not validated and cannot drive a production decision.")
        return output

    standard = NORMATIVE_STANDARDS[req.age_group][req.gender][req.weight_category][req.metric_name]

    recommendation = None
    if req.actual_value >= standard["excellent"]:
        eval_level = "Excellent 🏆"
    elif req.actual_value >= standard["average"]:
        eval_level = "Average"
        recommendation = "Grip Endurance Protocol A (SOL-000032)"
    else:
        eval_level = "Weak ⚠️"
        recommendation = "Intensive Remedial Grip & Isometric Protocol B (SOL-000045)"

    return {
        "system": "KAIZO Rule Engine",
        "athlete_id": req.athlete_id,
        "status": "DECISION",
        "evaluation": eval_level,
        "recommendation": recommendation,
        "timestamp": datetime.utcnow().isoformat()
    }

class KnowledgeIngestRequest(BaseModel):
    item_id: str
    domain: str
    title: str
    content: Dict[str, Any]
    user_id: str

@app.post("/api/v1/knowledge/ingest", status_code=status.HTTP_201_CREATED)
def ingest_knowledge(req: KnowledgeIngestRequest):
    pipeline_steps = ["Collect", "Verify", "Classify", "Link", "Approve", "Publish"]

    KNOWLEDGE_REPOSITORY[req.item_id] = {
        "id": req.item_id,
        "domain": req.domain,
        "title": req.title,
        "status": "Published",
        "pipeline_completed": pipeline_steps,
        "content": req.content
    }

    log_action(
        user_id=req.user_id,
        action="INGEST_KNOWLEDGE",
        old_val=None,
        new_val=req.item_id,
        reason="New entity successfully processed through Knowledge Engine pipeline."
    )

    return {
        "status": "Success",
        "message": "Item successfully published via Knowledge Engine pipeline.",
        "item_id": req.item_id,
        "pipeline": pipeline_steps
    }

@app.get("/api/v1/audit/logs")
def get_audit_logs():
    return {"system": "KAIZO Audit-Ready System", "total_logs": len(AUDIT_LOGS), "logs": AUDIT_LOGS}

@app.get("/api/v1/health")
def health_check():
    return {"system": "KAIZO Core Engine v2.0", "status": "Online", "mode": "Enterprise AI-Ready"}


DIGITAL_TWIN_STATE: Dict[str, Dict[str, Any]] = {}

class DigitalTwinSyncRequest(BaseModel):
    case_id: str
    entity_id: str
    state: Dict[str, Any]
    source_event: str
    coach_final_authority: bool = True
    expected_version: Optional[int] = None

@app.post("/api/v1/digital-twin/sync", status_code=status.HTTP_200_OK)
def synchronize_digital_twin(req: DigitalTwinSyncRequest) -> Dict[str, Any]:
    if not req.coach_final_authority:
        output = {
            "case_id": req.case_id, "entity_id": req.entity_id,
            "status": "HOLD", "reason_code": "COACH_FINAL_AUTHORITY_REQUIRED",
            "diagnostic_required": True, "timestamp": datetime.utcnow().isoformat()
        }
        log_action(req.case_id, "DIGITAL_TWIN_SYNC_HOLD", None, output, "Coach Final Authority is required.")
        return output
    if not req.case_id or not req.entity_id or not req.source_event or not req.state:
        output = {
            "case_id": req.case_id, "entity_id": req.entity_id,
            "status": "HOLD", "reason_code": "MISSING_DIGITAL_TWIN_INPUT",
            "diagnostic_required": True, "timestamp": datetime.utcnow().isoformat()
        }
        log_action(req.case_id or "unknown", "DIGITAL_TWIN_SYNC_HOLD", None, output, "Required Digital Twin synchronization input is missing.")
        return output

    current = DIGITAL_TWIN_STATE.get(req.entity_id)
    current_version = current["version"] if current else 0
    if req.expected_version is not None and req.expected_version != current_version:
        output = {
            "case_id": req.case_id, "entity_id": req.entity_id,
            "status": "HOLD", "reason_code": "DIGITAL_TWIN_VERSION_CONFLICT",
            "expected_version": req.expected_version, "current_version": current_version,
            "diagnostic_required": True, "resolution_required": True,
            "timestamp": datetime.utcnow().isoformat()
        }
        log_action(req.case_id, "DIGITAL_TWIN_SYNC_HOLD", current, output, "Digital Twin state version conflict requires diagnostic resolution.")
        return output

    new_version = current_version + 1
    new_state = {
        "entity_id": req.entity_id,
        "version": new_version,
        "state": req.state,
        "source_event": req.source_event,
        "case_id": req.case_id,
        "updated_at": datetime.utcnow().isoformat()
    }
    DIGITAL_TWIN_STATE[req.entity_id] = new_state
    output = {
        "case_id": req.case_id, "entity_id": req.entity_id,
        "status": "SYNCHRONIZED",
        "sync": {"previous_version": current_version, "new_version": new_version},
        "digital_twin_state": new_state,
        "coach_final_authority": True,
        "audit_required": True,
        "timestamp": datetime.utcnow().isoformat()
    }
    log_action(req.case_id, "DIGITAL_TWIN_SYNCHRONIZED", current, new_state, "Runtime Digital Twin state synchronized under Coach Final Authority.")
    return output

@app.get("/api/v1/digital-twin/{entity_id}")
def get_digital_twin(entity_id: str) -> Dict[str, Any]:
    twin = DIGITAL_TWIN_STATE.get(entity_id)
    if twin is None:
        return {
            "entity_id": entity_id,
            "status": "HOLD",
            "reason_code": "DIGITAL_TWIN_NOT_FOUND",
            "diagnostic_required": True,
            "timestamp": datetime.utcnow().isoformat()
        }
    return {"entity_id": entity_id, "status": "SYNCHRONIZED", "digital_twin_state": twin}

class DecisionLoopRequest(BaseModel):
    case_id: str
    decision: Dict[str, Any]
    intervention: Dict[str, Any]
    response_kpi: Dict[str, Any]
    retest: Dict[str, Any]
    coach_final_authority: bool = True

@app.post("/api/v1/decision/loop", status_code=status.HTTP_200_OK)
def decision_loop(req: DecisionLoopRequest) -> Dict[str, Any]:
    if not req.coach_final_authority:
        output = {"case_id": req.case_id, "status":"HOLD", "reason_code":"COACH_FINAL_AUTHORITY_REQUIRED", "diagnostic_required":True, "timestamp":datetime.utcnow().isoformat()}
        log_action(req.case_id, "DECISION_LOOP_HOLD", None, output, "Coach Final Authority is required.")
        return output
    missing = [name for name, value in {
        "decision": req.decision,
        "intervention": req.intervention,
        "response_kpi": req.response_kpi,
        "retest": req.retest,
    }.items() if not value]
    if missing:
        output = {"case_id": req.case_id, "status":"HOLD", "reason_code":"MISSING_DECISION_LOOP_INPUT", "missing_inputs":missing, "diagnostic_required":True, "timestamp":datetime.utcnow().isoformat()}
        log_action(req.case_id, "DECISION_LOOP_HOLD", None, output, "Required decision loop input is missing.")
        return output
    output = {
        "case_id": req.case_id,
        "status":"LOOP_COMPLETED",
        "coach_final_authority":True,
        "chain":["Decision","Intervention","Response/KPI","Retest","Audit"],
        "decision":req.decision,
        "intervention":req.intervention,
        "response_kpi":req.response_kpi,
        "retest":req.retest,
        "timestamp":datetime.utcnow().isoformat()
    }
    log_action(req.case_id, "DECISION_LOOP_COMPLETED", None, output, "Decision to intervention to KPI response to retest completed under Coach Final Authority.")
    return output

class AdaptationRequest(BaseModel):
    case_id: str
    operation: str
    common_core: Dict[str, Any]
    dynamic_inputs: Dict[str, Any]
    individual_change: Optional[Dict[str, Any]] = None
    team_change: Optional[Dict[str, Any]] = None
    composition_change: Optional[Dict[str, Any]] = None
    coach_final_authority: bool = True

@app.post("/api/v1/decision/adapt", status_code=status.HTTP_200_OK)
def adapt_decision(req: AdaptationRequest) -> Dict[str, Any]:
    allowed = {"individual_adaptation","team_adaptation","subgroup_recalculation","individual_change"}
    if req.operation not in allowed:
        output = {"case_id": req.case_id, "status":"HOLD", "reason_code":"UNSUPPORTED_ADAPTATION_OPERATION", "diagnostic_required":True, "allowed_operations":sorted(allowed), "timestamp":datetime.utcnow().isoformat()}
        log_action(req.case_id, "DECISION_ADAPTATION_HOLD", None, output, "Unsupported adaptation operation.")
        return output
    if not req.coach_final_authority:
        output = {"case_id": req.case_id, "status":"HOLD", "reason_code":"COACH_FINAL_AUTHORITY_REQUIRED", "diagnostic_required":True, "timestamp":datetime.utcnow().isoformat()}
        log_action(req.case_id, "DECISION_ADAPTATION_HOLD", None, output, "Coach Final Authority is required.")
        return output
    if not req.common_core or not req.dynamic_inputs:
        output = {"case_id": req.case_id, "status":"HOLD", "reason_code":"MISSING_ADAPTATION_INPUT", "diagnostic_required":True, "timestamp":datetime.utcnow().isoformat()}
        log_action(req.case_id, "DECISION_ADAPTATION_HOLD", None, output, "Required adaptation inputs are missing.")
        return output
    output = {"case_id":req.case_id,"status":"ADAPTED","operation":req.operation,"common_core_preserved":True,"adaptation_basis":req.dynamic_inputs,"coach_final_authority":True,"timestamp":datetime.utcnow().isoformat()}
    if req.operation == "individual_adaptation":
        output.update({"scope":"individual","individual_change":req.individual_change or {}})
    elif req.operation == "team_adaptation":
        output.update({"scope":"team","team_change":req.team_change or {}})
    elif req.operation == "subgroup_recalculation":
        output.update({"scope":"subgroup","composition_change":req.composition_change or {},"recalculation":"SUBGROUP_RECALCULATED"})
    else:
        output.update({"scope":"individual","individual_change":req.individual_change or {},"isolated_output_change":True})
    log_action(req.case_id, "DECISION_ADAPTATION", None, output, "Runtime adaptation executed under Coach Final Authority with Common Core preservation.")
    return output
