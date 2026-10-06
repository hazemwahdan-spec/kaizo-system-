"""Governed runtime for FEAT-057..060.
Evidence quality, provenance visibility, unsafe-action blocking, and escalation.
No execution is authorized; Coach Final Authority remains mandatory.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import persistence

router=APIRouter(prefix="/api/v1/evidence-safety",tags=["Evidence Safety"])
MEMORY:List[Dict[str,Any]]=[]

def now(): return datetime.now(timezone.utc).isoformat()
def authority(ok):
    if not ok: raise HTTPException(409,"Coach Final Authority is mandatory")

def audit(who,action,record):
    if persistence.is_postgres_enabled():
        persistence.append_audit(timestamp=record["timestamp"],who=who,action=action,old_value=None,new_value=record,why="Governed FEAT-057..060 runtime record.")

class EvidenceQualityRequest(BaseModel):
    subject_id:str; evidence_level:str; quality_status:str; evidence_refs:List[str]=Field(default_factory=list)
    assessed_by:str; coach_final_authority:bool=True

class ProvenanceRequest(BaseModel):
    subject_id:str; provenance_refs:List[str]; visible_to:List[str]=Field(default_factory=list)
    disclosed_by:str; coach_final_authority:bool=True

class UnsafeBlockRequest(BaseModel):
    action_id:str; block_reason:str; diagnostic:Dict[str,Any]
    evidence_refs:List[str]=Field(default_factory=list); blocked_by:str; coach_final_authority:bool=True

class EscalationRequest(BaseModel):
    subject_id:str; escalation_reason:str; review_state:str
    escalated_by:str; evidence_refs:List[str]=Field(default_factory=list); coach_final_authority:bool=True

@router.post("/feat-057/evidence-quality",status_code=201)
def evidence_quality(req:EvidenceQualityRequest):
    authority(req.coach_final_authority)
    if req.evidence_level not in {"E0","E1","E2","E3","E4","E5","E6"}: raise HTTPException(400,"evidence_level must be E0-E6")
    if not req.subject_id.strip() or not req.quality_status.strip() or not req.assessed_by.strip(): raise HTTPException(400,"subject_id, quality_status and assessed_by are required")
    if not req.evidence_refs: raise HTTPException(400,"evidence_refs are required")
    r={"feature_id":"FEAT-057","record_id":str(uuid4()),"subject_id":req.subject_id,"evidence_level":req.evidence_level,"quality_status":req.quality_status,"evidence_refs":req.evidence_refs,"assessed_by":req.assessed_by,"timestamp":now(),"coach_final_authority":True,"execution_authorized":False}
    MEMORY.append(r); audit(req.assessed_by,"FEAT-057_EVIDENCE_QUALITY_ASSESSED",r); return r

@router.post("/feat-058/provenance",status_code=201)
def provenance(req:ProvenanceRequest):
    authority(req.coach_final_authority)
    if not req.subject_id.strip() or not req.disclosed_by.strip(): raise HTTPException(400,"subject_id and disclosed_by are required")
    if not req.provenance_refs: raise HTTPException(400,"provenance_refs must be a non-empty list")
    r={"feature_id":"FEAT-058","record_id":str(uuid4()),"subject_id":req.subject_id,"provenance_refs":req.provenance_refs,"visible_to":req.visible_to,"disclosed_by":req.disclosed_by,"timestamp":now(),"coach_final_authority":True,"execution_authorized":False}
    MEMORY.append(r); audit(req.disclosed_by,"FEAT-058_PROVENANCE_VISIBLE",r); return r

@router.post("/feat-059/block",status_code=201)
def block(req:UnsafeBlockRequest):
    authority(req.coach_final_authority)
    if not req.action_id.strip() or not req.block_reason.strip() or not req.blocked_by.strip() or not req.diagnostic: raise HTTPException(400,"action_id, block_reason, diagnostic and blocked_by are required")
    if not req.evidence_refs: raise HTTPException(400,"evidence_refs are required")
    r={"feature_id":"FEAT-059","record_id":str(uuid4()),"action_id":req.action_id,"status":"HOLD","block_reason":req.block_reason,"diagnostic":req.diagnostic,"evidence_refs":req.evidence_refs,"blocked_by":req.blocked_by,"timestamp":now(),"coach_final_authority":True,"execution_authorized":False}
    MEMORY.append(r); audit(req.blocked_by,"FEAT-059_UNSAFE_ACTION_BLOCKED",r); return r

@router.post("/feat-060/escalate",status_code=201)
def escalate(req:EscalationRequest):
    authority(req.coach_final_authority)
    if req.review_state not in {"OPEN","UNDER_REVIEW","RESOLVED","REJECTED"}: raise HTTPException(400,"invalid review_state")
    if not req.subject_id.strip() or not req.escalation_reason.strip() or not req.escalated_by.strip(): raise HTTPException(400,"subject_id, escalation_reason and escalated_by are required")
    r={"feature_id":"FEAT-060","record_id":str(uuid4()),"subject_id":req.subject_id,"escalation_reason":req.escalation_reason,"review_state":req.review_state,"escalated_by":req.escalated_by,"evidence_refs":req.evidence_refs,"timestamp":now(),"coach_final_authority":True,"execution_authorized":False}
    MEMORY.append(r); audit(req.escalated_by,"FEAT-060_ESCALATION_RECORDED",r); return r
