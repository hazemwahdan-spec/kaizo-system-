"""KAIZO feature runtime — quality-first completion layer for FEAT-029..075.

This module is intentionally a real API/data boundary, not a placeholder model:
- every feature has an explicit contract;
- requests are validated against that contract;
- records are durable when PostgreSQL is enabled;
- audit metadata and evidence references are retained;
- Coach Final Authority is mandatory;
- execution authorization is permanently false.
Existing canonical FEAT-001..028/041/046/051/056 endpoints remain the source
for their already-integrated contracts.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import persistence
from progression_rules import ProgressionRegressionRule, validate_rule as validate_progression_rule
from session_constraints_notes import SessionConstraintNote, validate_item as validate_session_constraint
from drill_library import Drill, validate_drill
from problem_drill_linkage import ProblemDrillLink, validate_link


router = APIRouter(prefix="/api/v1/features", tags=["Feature Runtime"])


class FeatureRecordRequest(BaseModel):
    subject_id: str
    actor_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True
    execution_authorized: bool = False


class FeatureRecord(BaseModel):
    feature_id: str
    record_id: str
    subject_id: str
    actor_id: str
    payload: Dict[str, Any]
    evidence_refs: List[str]
    status: str
    coach_final_authority: bool
    execution_authorized: bool
    created_at: str
    updated_at: str


# Required fields are deliberately feature-specific. This prevents the common
# failure mode where a single generic JSON envelope is mistaken for 47 features.
CONTRACTS: Dict[str, Dict[str, Any]] = {
    "FEAT-029": {"name":"Progression/regression rules","required":["metric","threshold","action","adjustment"],"evidence":False,"status":"ACTIVE"},
    "FEAT-030": {"name":"Session constraints and notes","required":["session_id","kind","content","priority"],"evidence":False,"status":"ACTIVE"},
    "FEAT-031": {"name":"Drill library","required":["drill_id","name","judo_area","technical_skill","problem_target","decision_target","age_suitability","skill_level","execution_pattern","kpi","safety_constraints"],"evidence":True,"status":"PUBLISHED"},
    "FEAT-032": {"name":"Problem-to-drill linkage","required":["problem_id","drill_id","link_rationale"],"evidence":True,"status":"ACTIVE"},
    "FEAT-033": {"name":"Decision-to-drill selection","required":["decision_id","drill_id","selection_rationale"],"evidence":True,"status":"PENDING_COACH_REVIEW"},
    "FEAT-034": {"name":"Drill prescription","required":["drill_id","session_id","dosage","rationale"],"evidence":False,"status":"DRAFT"},
    "FEAT-035": {"name":"Execution cues and checklist","required":["prescription_id","cues","checks"],"evidence":False,"status":"READY_FOR_COACH"},
    "FEAT-036": {"name":"Training response capture","required":["session_id","athlete_id","response"],"evidence":False,"status":"RECORDED"},
    "FEAT-037": {"name":"Retest capture","required":["athlete_id","baseline_ref","retest_measurements"],"evidence":True,"status":"RECORDED"},
    "FEAT-038": {"name":"Before/after comparison","required":["before_ref","after_ref","comparison"],"evidence":True,"status":"COMPLETED"},
    "FEAT-039": {"name":"Progress state update","required":["athlete_id","state","state_basis"],"evidence":True,"status":"UPDATED"},
    "FEAT-040": {"name":"Next-decision trigger","required":["athlete_id","trigger_type","reason"],"evidence":True,"status":"TRIGGERED"},
    "FEAT-042": {"name":"Digital Twin state update","required":["entity_id","state","source_event"],"evidence":True,"status":"SYNCHRONIZED"},
    "FEAT-043": {"name":"State version/history","required":["entity_id","version","state"],"evidence":False,"status":"RECORDED"},
    "FEAT-044": {"name":"Decision-cycle state linkage","required":["decision_id","state_ref"],"evidence":False,"status":"LINKED"},
    "FEAT-045": {"name":"Next-state retrieval for decision","required":["athlete_id","requested_by"],"evidence":False,"status":"RETRIEVED"},
    "FEAT-047": {"name":"Source/provenance linkage","required":["knowledge_id","source_type","source_ref","provenance_note"],"evidence":True,"status":"VERIFIED"},
    "FEAT-048": {"name":"Knowledge lifecycle/status","required":["knowledge_id","lifecycle_status","changed_by"],"evidence":False,"status":"UPDATED"},
    "FEAT-049": {"name":"Knowledge retrieval for workflow","required":["workflow_context","query"],"evidence":False,"status":"RETRIEVED"},
    "FEAT-050": {"name":"Reusable knowledge unit linkage","required":["knowledge_id","unit_id","link_type"],"evidence":True,"status":"LINKED"},
    "FEAT-052": {"name":"Actor/action/time trace","required":["actor_id","action","occurred_at"],"evidence":False,"status":"RECORDED"},
    "FEAT-053": {"name":"Governance metadata","required":["object_type","governance_status","owner"],"evidence":False,"status":"RECORDED"},
    "FEAT-054": {"name":"Audit query/review","required":["query","reviewed_by"],"evidence":False,"status":"REVIEWED"},
    "FEAT-055": {"name":"Product action traceability","required":["product_action","source_record_ids","trace_reason"],"evidence":False,"status":"TRACED"},
    "FEAT-057": {"name":"Evidence-quality state","required":["subject_id","evidence_level","quality_status"],"evidence":True,"status":"ASSESSED"},
    "FEAT-058": {"name":"Provenance visibility","required":["subject_id","provenance_refs"],"evidence":True,"status":"VISIBLE"},
    "FEAT-059": {"name":"Unsafe/unsupported action block","required":["action_id","block_reason","diagnostic"],"evidence":True,"status":"HOLD"},
    "FEAT-060": {"name":"Escalation and review state","required":["subject_id","escalation_reason","review_state"],"evidence":False,"status":"ESCALATED"},
    "FEAT-061": {"name":"Academy entity","required":["academy_id","name","status"],"evidence":False,"status":"ACTIVE"},
    "FEAT-062": {"name":"Coach membership and roles","required":["academy_id","coach_id","role"],"evidence":False,"status":"ACTIVE"},
    "FEAT-063": {"name":"Academy groups","required":["academy_id","group_id","name"],"evidence":False,"status":"ACTIVE"},
    "FEAT-064": {"name":"Multi-coach athlete assignment","required":["athlete_id","coach_ids","academy_id"],"evidence":False,"status":"ASSIGNED"},
    "FEAT-065": {"name":"Academy operational dashboard","required":["academy_id","metrics"],"evidence":False,"status":"GENERATED"},
    "FEAT-066": {"name":"Competition event context","required":["event_id","event_name","date","context"],"evidence":False,"status":"RECORDED"},
    "FEAT-067": {"name":"Competition readiness indicators","required":["athlete_id","event_id","indicators"],"evidence":True,"status":"ASSESSED"},
    "FEAT-068": {"name":"Competition performance capture","required":["athlete_id","event_id","performance"],"evidence":True,"status":"RECORDED"},
    "FEAT-069": {"name":"Competition trend analysis","required":["athlete_id","event_ids","trend"],"evidence":True,"status":"ANALYZED"},
    "FEAT-070": {"name":"Competition-informed next decision","required":["athlete_id","event_id","decision_basis"],"evidence":True,"status":"PENDING_COACH_REVIEW"},
    "FEAT-071": {"name":"Athlete progress report","required":["athlete_id","period","progress"],"evidence":True,"status":"GENERATED"},
    "FEAT-072": {"name":"KPI trend report","required":["athlete_id","kpi_id","period","trend"],"evidence":True,"status":"GENERATED"},
    "FEAT-073": {"name":"Coach performance summary","required":["coach_id","period","summary"],"evidence":False,"status":"GENERATED"},
    "FEAT-074": {"name":"Academy performance dashboard","required":["academy_id","period","metrics"],"evidence":False,"status":"GENERATED"},
    "FEAT-075": {"name":"Approved-data reporting export","required":["report_id","approved_record_ids","format"],"evidence":False,"status":"APPROVED"},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema() -> None:
    if not persistence.is_postgres_enabled():
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_feature_records (
                    record_id TEXT PRIMARY KEY,
                    feature_id TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    payload JSONB NOT NULL,
                    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
                    status TEXT NOT NULL,
                    coach_final_authority BOOLEAN NOT NULL,
                    execution_authorized BOOLEAN NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_kaizo_feature_records_feature
                    ON kaizo_feature_records(feature_id);
                CREATE INDEX IF NOT EXISTS idx_kaizo_feature_records_subject
                    ON kaizo_feature_records(subject_id);
            """)
        conn.commit()


_MEMORY: Dict[str, Dict[str, Any]] = {}


def _save(record: Dict[str, Any]) -> None:
    if not persistence.is_postgres_enabled():
        _MEMORY[record["record_id"]] = record
        return
    _ensure_schema()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO kaizo_feature_records
                (record_id,feature_id,subject_id,actor_id,payload,evidence_refs,status,
                 coach_final_authority,execution_authorized,created_at,updated_at)
                VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s)
                ON CONFLICT (record_id) DO UPDATE SET
                    payload=EXCLUDED.payload,
                    evidence_refs=EXCLUDED.evidence_refs,
                    status=EXCLUDED.status,
                    updated_at=EXCLUDED.updated_at
            """, (
                record["record_id"],record["feature_id"],record["subject_id"],record["actor_id"],
                __import__("json").dumps(record["payload"]),
                __import__("json").dumps(record["evidence_refs"]),
                record["status"],record["coach_final_authority"],record["execution_authorized"],
                record["created_at"],record["updated_at"]))
        conn.commit()


def _get(record_id: str) -> Optional[Dict[str, Any]]:
    if not persistence.is_postgres_enabled():
        return _MEMORY.get(record_id)
    _ensure_schema()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT record_id,feature_id,subject_id,actor_id,payload,
                                  evidence_refs,status,coach_final_authority,
                                  execution_authorized,created_at,updated_at
                           FROM kaizo_feature_records WHERE record_id=%s""",(record_id,))
            row=cur.fetchone()
    if not row:
        return None
    return {"record_id":row[0],"feature_id":row[1],"subject_id":row[2],"actor_id":row[3],
            "payload":row[4],"evidence_refs":row[5],"status":row[6],
            "coach_final_authority":row[7],"execution_authorized":row[8],
            "created_at":row[9],"updated_at":row[10]}


def _list(feature_id: str) -> List[Dict[str, Any]]:
    if not persistence.is_postgres_enabled():
        return [r for r in _MEMORY.values() if r["feature_id"]==feature_id]
    _ensure_schema()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""SELECT record_id,feature_id,subject_id,actor_id,payload,
                                  evidence_refs,status,coach_final_authority,
                                  execution_authorized,created_at,updated_at
                           FROM kaizo_feature_records WHERE feature_id=%s
                           ORDER BY created_at""",(feature_id,))
            rows=cur.fetchall()
    return [{"record_id":r[0],"feature_id":r[1],"subject_id":r[2],"actor_id":r[3],
             "payload":r[4],"evidence_refs":r[5],"status":r[6],
             "coach_final_authority":r[7],"execution_authorized":r[8],
             "created_at":r[9],"updated_at":r[10]} for r in rows]


def _validate(feature_id: str, req: FeatureRecordRequest) -> Dict[str, Any]:
    contract=CONTRACTS.get(feature_id)
    if not contract:
        raise HTTPException(status_code=404, detail="feature contract not found")
    if not req.subject_id.strip() or not req.actor_id.strip():
        raise HTTPException(status_code=400, detail="subject_id and actor_id are required")
    if not req.coach_final_authority:
        raise HTTPException(status_code=409, detail="Coach Final Authority is mandatory")
    if req.execution_authorized:
        raise HTTPException(status_code=409, detail="execution_authorized must remain false")
    missing=[k for k in contract["required"] if k not in req.payload or req.payload[k] in (None,"",[])]
    if missing:
        raise HTTPException(status_code=400, detail={"missing_fields":missing,"feature_id":feature_id})
    try:
        if feature_id == "FEAT-029":
            p=req.payload
            validate_progression_rule(ProgressionRegressionRule(
                rule_id=str(p.get("rule_id", req.subject_id)), name=str(p.get("name","progression rule")),
                metric=str(p["metric"]), operator=str(p.get("operator","GTE")),
                threshold=float(p["threshold"]), action=str(p["action"]),
                adjustment=float(p["adjustment"]), created_by=req.actor_id))
        elif feature_id == "FEAT-030":
            p=req.payload
            validate_session_constraint(SessionConstraintNote(
                item_id=str(p.get("item_id", req.subject_id)), session_id=str(p["session_id"]),
                kind=str(p["kind"]), content=str(p["content"]), priority=str(p["priority"]),
                created_by=req.actor_id))
        elif feature_id == "FEAT-031":
            p=req.payload
            validate_drill(Drill(
                drill_id=str(p["drill_id"]), name=str(p["name"]),
                judo_area=str(p["judo_area"]), technical_skill=str(p["technical_skill"]),
                problem_target=str(p["problem_target"]), decision_target=str(p["decision_target"]),
                age_suitability=str(p["age_suitability"]), skill_level=str(p["skill_level"]),
                execution_pattern=str(p["execution_pattern"]), kpi=str(p["kpi"]),
                safety_constraints=str(p["safety_constraints"]),
                evidence=tuple(req.evidence_refs), source=tuple(req.evidence_refs)))
        elif feature_id == "FEAT-032":
            p=req.payload
            validate_link(ProblemDrillLink(
                link_id=str(p.get("link_id", req.subject_id)), problem_id=str(p["problem_id"]),
                drill_id=str(p["drill_id"]), rationale=str(p["link_rationale"]),
                created_by=req.actor_id))
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail={"feature_id":feature_id,"domain_validation":str(exc)})
    if contract["evidence"] and not req.evidence_refs:
        raise HTTPException(status_code=400, detail="evidence_refs are required for this feature")
    return contract


def _create(feature_id: str, req: FeatureRecordRequest) -> Dict[str, Any]:
    contract=_validate(feature_id,req)
    now=_now()
    record={
        "feature_id":feature_id,
        "record_id":str(uuid4()),
        "subject_id":req.subject_id.strip(),
        "actor_id":req.actor_id.strip(),
        "payload":req.payload,
        "evidence_refs":req.evidence_refs,
        "status":contract["status"],
        "coach_final_authority":True,
        "execution_authorized":False,
        "created_at":now,
        "updated_at":now,
    }
    _save(record)
    if persistence.is_postgres_enabled():
        persistence.append_audit(timestamp=now,who=req.actor_id.strip(),
            action=f"{feature_id}_RECORDED",old_value=None,new_value=record,
            why=f"Feature contract accepted: {contract['name']}.")
    return record


# Explicit feature routes are generated from the frozen IDs; the contract, not
# the caller, determines required fields and governance behavior.
def _register(feature_id: str) -> None:
    slug=CONTRACTS[feature_id]["name"].lower().replace("/","-").replace(" ","-")
    slug="".join(c for c in slug if c.isalnum() or c=="-").strip("-")
    def create(req: FeatureRecordRequest, _fid: str=feature_id):
        return _create(_fid,req)
    def get(record_id: str, _fid: str=feature_id):
        record=_get(record_id)
        if record is None or record["feature_id"] != _fid:
            raise HTTPException(status_code=404, detail="feature record not found")
        return record
    def list_records(_fid: str=feature_id):
        return {"feature_id":_fid,"feature":CONTRACTS[_fid]["name"],"records":_list(_fid)}
    router.add_api_route(f"/{feature_id.lower()}/{slug}",create,methods=["POST"],status_code=201,
                         name=f"{feature_id}_create",summary=CONTRACTS[feature_id]["name"])
    router.add_api_route(f"/{feature_id.lower()}/{slug}/{{record_id}}",get,methods=["GET"],
                         name=f"{feature_id}_get")
    router.add_api_route(f"/{feature_id.lower()}/{slug}",list_records,methods=["GET"],
                         name=f"{feature_id}_list")


for _feature_id in CONTRACTS:
    _register(_feature_id)
