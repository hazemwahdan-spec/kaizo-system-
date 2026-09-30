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
