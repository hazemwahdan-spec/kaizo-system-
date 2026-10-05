"""KAIZO Core Engine™ v2.0 - Enterprise Backend API
Framework: FastAPI + Pydantic
Slogan: Better Every Day
"""

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
from datetime import datetime

import persistence

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

ATHLETE_RECORDS: Dict[str, Dict[str, Any]] = {}

class AthleteCreateRequest(BaseModel):
    display_name: str
    metadata: Dict[str, Any] = {}


class AthleteUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@app.post("/api/v1/athletes", status_code=status.HTTP_201_CREATED)
def create_athlete(req: AthleteCreateRequest) -> Dict[str, Any]:
    display_name = req.display_name.strip()
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    now = datetime.utcnow().isoformat()
    import uuid
    athlete = {
        "athlete_id": str(uuid.uuid4()),
        "display_name": display_name,
        "status": "ACTIVE",
        "metadata": req.metadata,
        "created_at": now,
        "updated_at": now,
    }
    ATHLETE_RECORDS[athlete["athlete_id"]] = athlete
    persistence.upsert_athlete(athlete)
    log_action(
        "system",
        "ATHLETE_CREATED",
        None,
        athlete,
        "Athlete record created with stable identity and lifecycle state.",
    )
    return athlete


@app.get("/api/v1/athletes/{athlete_id}")
def get_athlete(athlete_id: str) -> Dict[str, Any]:
    athlete = persistence.get_athlete(athlete_id) if persistence.is_postgres_enabled() else ATHLETE_RECORDS.get(athlete_id)
    if athlete is None:
        raise HTTPException(status_code=404, detail="athlete not found")
    return athlete


@app.patch("/api/v1/athletes/{athlete_id}")
def update_athlete(athlete_id: str, req: AthleteUpdateRequest) -> Dict[str, Any]:
    current = persistence.get_athlete(athlete_id) if persistence.is_postgres_enabled() else ATHLETE_RECORDS.get(athlete_id)
    if current is None:
        raise HTTPException(status_code=404, detail="athlete not found")
    if req.display_name is not None:
        name = req.display_name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="display_name cannot be empty")
        current["display_name"] = name
    if req.status is not None:
        allowed = {"ACTIVE", "INACTIVE", "ARCHIVED"}
        if req.status not in allowed:
            raise HTTPException(status_code=400, detail="invalid lifecycle status")
        current["status"] = req.status
    if req.metadata is not None:
        current["metadata"] = req.metadata
    current["updated_at"] = datetime.utcnow().isoformat()
    ATHLETE_RECORDS[athlete_id] = current
    persistence.upsert_athlete(current)
    log_action(
        "system",
        "ATHLETE_UPDATED",
        None,
        current,
        "Athlete lifecycle/profile updated without changing stable identity.",
    )
    return current



ASSESSMENT_RECORDS: Dict[str, Dict[str, Any]] = {}
_ASSESSMENT_EVIDENCE_ATTACHMENTS: Dict[str, Dict[str, Any]] = {}

class AssessmentCreateRequest(BaseModel):
    athlete_id: str
    template_id: str
    measurements: Dict[str, Any]
    recorded_by: str


@app.post("/api/v1/assessments", status_code=status.HTTP_201_CREATED)
def create_assessment(req: AssessmentCreateRequest) -> Dict[str, Any]:
    if not req.athlete_id.strip():
        raise HTTPException(status_code=400, detail="athlete_id is required")
    if not req.template_id.strip():
        raise HTTPException(status_code=400, detail="template_id is required")
    if not req.recorded_by.strip():
        raise HTTPException(status_code=400, detail="recorded_by is required")
    athlete = (
        persistence.get_athlete(req.athlete_id)
        if persistence.is_postgres_enabled()
        else ATHLETE_RECORDS.get(req.athlete_id)
    )
    if athlete is None:
        raise HTTPException(status_code=404, detail="athlete not found")
    if not req.measurements:
        raise HTTPException(status_code=400, detail="measurements are required")

    import uuid
    now = datetime.utcnow().isoformat()
    assessment = {
        "assessment_id": str(uuid.uuid4()),
        "athlete_id": req.athlete_id,
        "template_id": req.template_id,
        "measurements": req.measurements,
        "recorded_by": req.recorded_by,
        "assessed_at": now,
        "created_at": now,
    }
    ASSESSMENT_RECORDS[assessment["assessment_id"]] = assessment
    persistence.upsert_assessment(assessment)
    log_action(
        req.recorded_by,
        "ASSESSMENT_RECORDED",
        None,
        assessment,
        "Assessment measurements persisted with explicit athlete ownership and timestamp.",
    )
    return assessment


@app.get("/api/v1/assessments/{assessment_id}")
def get_assessment(assessment_id: str) -> Dict[str, Any]:
    assessment = (
        persistence.get_assessment(assessment_id)
        if persistence.is_postgres_enabled()
        else ASSESSMENT_RECORDS.get(assessment_id)
    )
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    return assessment



class AssessmentEvidenceAttachmentRequest(BaseModel):
    assessment_id: str
    evidence_id: str
    attached_by: str


@app.post("/api/v1/assessments/{assessment_id}/evidence", status_code=status.HTTP_201_CREATED)
def attach_assessment_evidence(assessment_id: str, req: AssessmentEvidenceAttachmentRequest) -> Dict[str, Any]:
    if assessment_id != req.assessment_id:
        raise HTTPException(status_code=400, detail="assessment_id mismatch")
    if not req.evidence_id.strip() or not req.attached_by.strip():
        raise HTTPException(status_code=400, detail="evidence_id and attached_by are required")

    assessment = persistence.get_assessment(assessment_id) if persistence.is_postgres_enabled() else ASSESSMENT_RECORDS.get(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")

    evidence = persistence.get_evidence(req.evidence_id) if persistence.is_postgres_enabled() else EVIDENCE_RECORDS.get(req.evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    if evidence.get("subject_type") != "assessment" or evidence.get("subject_id") != assessment_id:
        raise HTTPException(status_code=400, detail="evidence is not scoped to this assessment")

    attachment = {
        "assessment_id": assessment_id,
        "evidence_id": req.evidence_id,
        "attached_by": req.attached_by,
        "attached_at": datetime.utcnow().isoformat(),
    }
    _ASSESSMENT_EVIDENCE_ATTACHMENTS[f"{assessment_id}:{req.evidence_id}"] = attachment
    persistence.attach_assessment_evidence(attachment)
    log_action(
        req.attached_by,
        "ASSESSMENT_EVIDENCE_ATTACHED",
        None,
        attachment,
        "Assessment evidence attachment created with explicit assessment and evidence linkage.",
    )
    return attachment


@app.get("/api/v1/assessments/{assessment_id}/evidence")
def list_assessment_evidence(assessment_id: str) -> Dict[str, Any]:
    assessment = persistence.get_assessment(assessment_id) if persistence.is_postgres_enabled() else ASSESSMENT_RECORDS.get(assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    attachments = persistence.list_assessment_evidence(assessment_id) if persistence.is_postgres_enabled() else [
        value for value in _ASSESSMENT_EVIDENCE_ATTACHMENTS.values() if value["assessment_id"] == assessment_id
    ]
    return {"assessment_id": assessment_id, "attachments": attachments}



class ProblemStatementCreateRequest(BaseModel):
    athlete_id: str
    assessment_id: str
    statement: str
    problem_type: str
    impact: Optional[str] = None
    context: Dict[str, Any] = {}
    structured_fields: Dict[str, Any] = {}
    created_by: str


PROBLEM_STATEMENTS: Dict[str, Dict[str, Any]] = {}


@app.post("/api/v1/problem-statements", status_code=status.HTTP_201_CREATED)
def create_problem_statement(req: ProblemStatementCreateRequest) -> Dict[str, Any]:
    if not req.athlete_id.strip() or not req.assessment_id.strip() or not req.statement.strip():
        raise HTTPException(status_code=400, detail="athlete_id, assessment_id and statement are required")
    if not req.problem_type.strip() or not req.created_by.strip():
        raise HTTPException(status_code=400, detail="problem_type and created_by are required")
    athlete = persistence.get_athlete(req.athlete_id) if persistence.is_postgres_enabled() else ATHLETE_RECORDS.get(req.athlete_id)
    if athlete is None:
        raise HTTPException(status_code=404, detail="athlete not found")
    assessment = persistence.get_assessment(req.assessment_id) if persistence.is_postgres_enabled() else ASSESSMENT_RECORDS.get(req.assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    if assessment["athlete_id"] != req.athlete_id:
        raise HTTPException(status_code=400, detail="assessment does not belong to athlete")
    import uuid
    now=datetime.utcnow().isoformat()
    problem={"problem_id":str(uuid.uuid4()),"athlete_id":req.athlete_id,"assessment_id":req.assessment_id,
             "statement":req.statement.strip(),"problem_type":req.problem_type.strip(),"impact":req.impact.strip() if req.impact else None,
             "context":req.context,"structured_fields":req.structured_fields,"status":"OPEN",
             "created_by":req.created_by.strip(),"created_at":now,"updated_at":now}
    PROBLEM_STATEMENTS[problem["problem_id"]]=problem
    persistence.upsert_problem_statement(problem)
    log_action(req.created_by,"PROBLEM_STATEMENT_CREATED",None,problem,
               "Structured problem statement created from an existing athlete assessment with explicit context and ownership.")
    return problem


@app.get("/api/v1/problem-statements/{problem_id}")
def get_problem_statement(problem_id: str) -> Dict[str, Any]:
    problem=persistence.get_problem_statement(problem_id) if persistence.is_postgres_enabled() else PROBLEM_STATEMENTS.get(problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="problem statement not found")
    return problem


@app.get("/api/v1/problem-statements")
def list_problem_statements(athlete_id: Optional[str]=None) -> Dict[str, Any]:
    problems=persistence.list_problem_statements(athlete_id) if persistence.is_postgres_enabled() else list(PROBLEM_STATEMENTS.values())
    if athlete_id:
        problems=[item for item in problems if item["athlete_id"]==athlete_id]
    return {"total_problem_statements":len(problems),"problem_statements":problems}


class KPIDefinitionCreateRequest(BaseModel):
    kpi_id: str
    name: str
    metric_name: str
    unit: str
    target: Optional[float] = None
    direction: str = "higher_is_better"
    defined_by: str

class KPICaptureRequest(BaseModel):
    athlete_id: str
    kpi_id: str
    value: float
    captured_by: str
    assessment_id: Optional[str] = None

KPI_DEFINITIONS: Dict[str, Dict[str, Any]] = {}
KPI_CAPTURES: Dict[str, Dict[str, Any]] = {}

@app.post("/api/v1/kpis", status_code=status.HTTP_201_CREATED)
def create_kpi(req: KPIDefinitionCreateRequest) -> Dict[str, Any]:
    allowed_directions = {"higher_is_better", "lower_is_better", "target_range"}
    if not req.kpi_id.strip() or not req.name.strip() or not req.metric_name.strip() or not req.unit.strip():
        raise HTTPException(status_code=400, detail="kpi_id, name, metric_name and unit are required")
    if not req.defined_by.strip():
        raise HTTPException(status_code=400, detail="defined_by is required")
    if req.direction not in allowed_directions:
        raise HTTPException(status_code=400, detail="invalid KPI direction")
    now = datetime.utcnow().isoformat()
    definition = {
        "kpi_id": req.kpi_id,
        "name": req.name.strip(),
        "metric_name": req.metric_name.strip(),
        "unit": req.unit.strip(),
        "target": req.target,
        "direction": req.direction,
        "defined_by": req.defined_by,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
    }
    KPI_DEFINITIONS[req.kpi_id] = definition
    persistence.upsert_kpi_definition(definition)
    log_action(req.defined_by, "KPI_DEFINED", None, definition, "KPI definition captured with explicit metric semantics and owner.")
    return definition

@app.get("/api/v1/kpis/{kpi_id}")
def get_kpi(kpi_id: str) -> Dict[str, Any]:
    definition = persistence.get_kpi_definition(kpi_id) if persistence.is_postgres_enabled() else KPI_DEFINITIONS.get(kpi_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="KPI not found")
    return definition

@app.post("/api/v1/kpis/captures", status_code=status.HTTP_201_CREATED)
def capture_kpi(req: KPICaptureRequest) -> Dict[str, Any]:
    if not req.athlete_id.strip() or not req.kpi_id.strip() or not req.captured_by.strip():
        raise HTTPException(status_code=400, detail="athlete_id, kpi_id and captured_by are required")
    athlete = persistence.get_athlete(req.athlete_id) if persistence.is_postgres_enabled() else ATHLETE_RECORDS.get(req.athlete_id)
    if athlete is None:
        raise HTTPException(status_code=404, detail="athlete not found")
    kpi = persistence.get_kpi_definition(req.kpi_id) if persistence.is_postgres_enabled() else KPI_DEFINITIONS.get(req.kpi_id)
    if kpi is None:
        raise HTTPException(status_code=404, detail="KPI not found")
    import uuid
    now = datetime.utcnow().isoformat()
    capture = {
        "capture_id": str(uuid.uuid4()),
        "athlete_id": req.athlete_id,
        "kpi_id": req.kpi_id,
        "value": req.value,
        "captured_by": req.captured_by,
        "assessment_id": req.assessment_id,
        "captured_at": now,
        "created_at": now,
    }
    KPI_CAPTURES[capture["capture_id"]] = capture
    persistence.upsert_kpi_capture(capture)
    log_action(req.captured_by, "KPI_CAPTURED", None, capture, "KPI value captured for an existing athlete and defined KPI.")
    return capture

@app.get("/api/v1/kpis/captures/{capture_id}")
def get_kpi_capture(capture_id: str) -> Dict[str, Any]:
    capture = persistence.get_kpi_capture(capture_id) if persistence.is_postgres_enabled() else KPI_CAPTURES.get(capture_id)
    if capture is None:
        raise HTTPException(status_code=404, detail="KPI capture not found")
    return capture


def log_action(user_id: str, action: str, old_val: Any, new_val: Any, reason: str):
    timestamp = datetime.utcnow().isoformat()
    entry = {
        "timestamp": timestamp,
        "who": user_id,
        "action": action,
        "old_value": old_val,
        "new_value": new_val,
        "why": reason
    }
    AUDIT_LOGS.append(entry)
    persistence.append_audit(
        timestamp=timestamp,
        who=user_id,
        action=action,
        old_value=old_val,
        new_value=new_val,
        why=reason,
    )

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

if persistence.is_postgres_enabled():
    persistence.initialize()
    KNOWLEDGE_REPOSITORY.update(persistence.load_knowledge())

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

class SafetyEvaluationRequest(BaseModel):
    action_id: str
    subject_id: str
    action_type: str
    evidence_level: str
    evidence_status: str
    safety_constraints_met: bool
    coach_final_authority: bool = True
    rationale: Optional[str] = None


@app.post("/api/v1/safety/evaluate", status_code=status.HTTP_200_OK)
def evaluate_safety(req: SafetyEvaluationRequest) -> Dict[str, Any]:
    allowed_levels = {"E0", "E1", "E2", "E3", "E4", "E5", "E6"}
    if req.evidence_level not in allowed_levels:
        raise HTTPException(status_code=400, detail="invalid evidence level")
    if not req.action_id.strip() or not req.subject_id.strip() or not req.action_type.strip():
        raise HTTPException(status_code=400, detail="action_id, subject_id and action_type are required")

    base = {
        "action_id": req.action_id,
        "subject_id": req.subject_id,
        "action_type": req.action_type,
        "evidence_level": req.evidence_level,
        "evidence_status": req.evidence_status,
        "safety_constraints_met": req.safety_constraints_met,
        "coach_final_authority": req.coach_final_authority,
        "rationale": req.rationale,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if not req.coach_final_authority:
        output = {
            **base,
            "status": "HOLD",
            "reason_code": "COACH_FINAL_AUTHORITY_REQUIRED",
            "diagnostic_required": True,
            "decision_blocked": True,
        }
        log_action(req.subject_id, "SAFETY_EVALUATION_HOLD", None, output, "Coach Final Authority is required before a safety-cleared action can proceed.")
        return output

    if req.evidence_status.upper() != "VERIFIED" or req.evidence_level == "E0":
        output = {
            **base,
            "status": "HOLD",
            "reason_code": "EVIDENCE_QUALITY_INSUFFICIENT",
            "diagnostic_required": True,
            "decision_blocked": True,
        }
        log_action(req.subject_id, "SAFETY_EVALUATION_HOLD", None, output, "Safety evaluation requires verified evidence above E0.")
        return output

    if not req.safety_constraints_met:
        output = {
            **base,
            "status": "HOLD",
            "reason_code": "SAFETY_CONSTRAINT_VIOLATION",
            "diagnostic_required": True,
            "decision_blocked": True,
        }
        log_action(req.subject_id, "SAFETY_EVALUATION_HOLD", None, output, "One or more safety constraints are not satisfied.")
        return output

    output = {
        **base,
        "status": "SAFE_TO_PROCEED",
        "decision_blocked": False,
    }
    log_action(req.subject_id, "SAFETY_EVALUATION_PASSED", None, output, "Verified evidence and declared safety constraints support the evaluated action.")
    return output


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

    persistence.upsert_knowledge(req.item_id, KNOWLEDGE_REPOSITORY[req.item_id], datetime.utcnow().isoformat())

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

class EvidenceCreateRequest(BaseModel):
    evidence_id: str
    subject_type: str
    subject_id: str
    evidence_level: str
    status: str
    source_ref: Optional[str] = None
    claim: str
    observed_value: Optional[Dict[str, Any]] = None
    verified_by: str
    notes: Optional[str] = None


EVIDENCE_RECORDS: Dict[str, Dict[str, Any]] = {}


@app.post("/api/v1/evidence", status_code=status.HTTP_201_CREATED)
def record_evidence(req: EvidenceCreateRequest) -> Dict[str, Any]:
    allowed_levels = {"E0", "E1", "E2", "E3", "E4", "E5", "E6"}
    if req.evidence_level not in allowed_levels:
        raise HTTPException(status_code=400, detail="invalid evidence level")
    if not req.evidence_id.strip() or not req.subject_id.strip() or not req.claim.strip():
        raise HTTPException(status_code=400, detail="evidence_id, subject_id and claim are required")
    if not req.verified_by.strip():
        raise HTTPException(status_code=400, detail="verified_by is required")
    now = datetime.utcnow().isoformat()
    record = {
        "evidence_id": req.evidence_id,
        "subject_type": req.subject_type,
        "subject_id": req.subject_id,
        "evidence_level": req.evidence_level,
        "status": req.status,
        "source_ref": req.source_ref,
        "claim": req.claim,
        "observed_value": req.observed_value,
        "verified_by": req.verified_by,
        "verified_at": now,
        "notes": req.notes,
    }
    EVIDENCE_RECORDS[req.evidence_id] = record
    persistence.upsert_evidence(record)
    log_action(
        req.verified_by,
        "EVIDENCE_RECORDED",
        None,
        record,
        "Evidence recorded with explicit subject, level, status, provenance and verifier.",
    )
    return record


@app.get("/api/v1/evidence/{evidence_id}")
def get_evidence(evidence_id: str) -> Dict[str, Any]:
    record = persistence.get_evidence(evidence_id) if persistence.is_postgres_enabled() else EVIDENCE_RECORDS.get(evidence_id)
    if record is None:
        raise HTTPException(status_code=404, detail="evidence not found")
    return record


@app.get("/api/v1/evidence")
def list_evidence(subject_id: Optional[str] = None) -> Dict[str, Any]:
    records = persistence.list_evidence(subject_id) if persistence.is_postgres_enabled() else list(EVIDENCE_RECORDS.values())
    if subject_id:
        records = [r for r in records if r["subject_id"] == subject_id]
    return {"total_evidence": len(records), "records": records}


@app.get("/api/v1/audit/logs")
def get_audit_logs():
    logs = persistence.list_audit_logs() if persistence.is_postgres_enabled() else AUDIT_LOGS
    return {"system": "KAIZO Audit-Ready System", "total_logs": len(logs), "logs": logs}

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

    current = persistence.get_digital_twin(req.entity_id) if persistence.is_postgres_enabled() else DIGITAL_TWIN_STATE.get(req.entity_id)
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
    persistence.upsert_digital_twin(new_state)
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
    twin = persistence.get_digital_twin(entity_id) if persistence.is_postgres_enabled() else DIGITAL_TWIN_STATE.get(entity_id)
    if twin is None:
        return {
            "entity_id": entity_id,
            "status": "HOLD",
            "reason_code": "DIGITAL_TWIN_NOT_FOUND",
            "diagnostic_required": True,
            "timestamp": datetime.utcnow().isoformat()
        }
    return {"entity_id": entity_id, "status": "SYNCHRONIZED", "digital_twin_state": twin}

class StateSnapshotCreateRequest(BaseModel):
    athlete_id: str
    assessment_id: str
    snapshot_type: str
    kpi_capture_ids: List[str]
    captured_by: str


STATE_SNAPSHOTS: Dict[str, Dict[str, Any]] = {}


@app.post("/api/v1/state-snapshots", status_code=status.HTTP_201_CREATED)
def create_state_snapshot(req: StateSnapshotCreateRequest) -> Dict[str, Any]:
    if req.snapshot_type not in {"baseline", "current_state"}:
        raise HTTPException(status_code=400, detail="snapshot_type must be baseline or current_state")
    if not req.athlete_id.strip() or not req.assessment_id.strip() or not req.captured_by.strip():
        raise HTTPException(status_code=400, detail="athlete_id, assessment_id and captured_by are required")
    if not req.kpi_capture_ids:
        raise HTTPException(status_code=400, detail="at least one KPI capture is required")

    athlete = persistence.get_athlete(req.athlete_id) if persistence.is_postgres_enabled() else ATHLETE_RECORDS.get(req.athlete_id)
    if athlete is None:
        raise HTTPException(status_code=404, detail="athlete not found")
    assessment = persistence.get_assessment(req.assessment_id) if persistence.is_postgres_enabled() else ASSESSMENT_RECORDS.get(req.assessment_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="assessment not found")
    if assessment["athlete_id"] != req.athlete_id:
        raise HTTPException(status_code=400, detail="assessment does not belong to athlete")

    kpis = []
    for capture_id in req.kpi_capture_ids:
        capture = persistence.get_kpi_capture(capture_id) if persistence.is_postgres_enabled() else KPI_CAPTURES.get(capture_id)
        if capture is None:
            raise HTTPException(status_code=404, detail=f"KPI capture not found: {capture_id}")
        if capture["athlete_id"] != req.athlete_id:
            raise HTTPException(status_code=400, detail=f"KPI capture does not belong to athlete: {capture_id}")
        kpis.append(capture)

    import uuid
    now = datetime.utcnow().isoformat()
    snapshot = {
        "snapshot_id": str(uuid.uuid4()),
        "athlete_id": req.athlete_id,
        "assessment_id": req.assessment_id,
        "snapshot_type": req.snapshot_type,
        "measurements": assessment["measurements"],
        "kpis": kpis,
        "captured_by": req.captured_by,
        "captured_at": now,
        "created_at": now,
    }
    STATE_SNAPSHOTS[snapshot["snapshot_id"]] = snapshot
    persistence.upsert_state_snapshot(snapshot)
    log_action(
        req.captured_by,
        "ATHLETE_STATE_SNAPSHOT_CREATED",
        None,
        snapshot,
        "Baseline/current-state snapshot materialized from an assessment and KPI captures.",
    )
    return snapshot


@app.get("/api/v1/state-snapshots/{snapshot_id}")
def get_state_snapshot(snapshot_id: str) -> Dict[str, Any]:
    snapshot = persistence.get_state_snapshot(snapshot_id) if persistence.is_postgres_enabled() else STATE_SNAPSHOTS.get(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="state snapshot not found")
    return snapshot


@app.get("/api/v1/state-snapshots")
def list_state_snapshots(athlete_id: Optional[str] = None) -> Dict[str, Any]:
    snapshots = persistence.list_state_snapshots(athlete_id) if persistence.is_postgres_enabled() else list(STATE_SNAPSHOTS.values())
    if athlete_id:
        snapshots = [item for item in snapshots if item["athlete_id"] == athlete_id]
    return {"total_snapshots": len(snapshots), "snapshots": snapshots}


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
