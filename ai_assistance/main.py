from datetime import datetime, timezone
from enum import Enum
from fastapi import FastAPI
from pydantic import BaseModel, Field

app=FastAPI(title="KAIZO P16 Governed AI Assistance",version="1.0")
audit_log=[]

def audit_event(event,payload):
    audit_log.append({"event":event,"timestamp":datetime.now(timezone.utc).isoformat(),**payload})

class Disposition(str,Enum):
    pending="pending"
    accepted="accepted"
    rejected="rejected"

class AssistanceRequest(BaseModel):
    request_id:str=Field(min_length=1)
    actor_id:str=Field(min_length=1)
    actor_role:str=Field(min_length=1)
    academy_id:str=Field(min_length=1)
    task:str=Field(min_length=1)
    evidence_refs:list[str]=[]
    child_data:bool=False

class DispositionRequest(BaseModel):
    request_id:str
    coach_id:str
    disposition:Disposition
    note:str=""

@app.get("/health")
def health():
    return {"status":"ok","service":"kaizo-p16-ai-assistance","governed":True,"coach_final_authority":True,"autonomous_decision":False}

@app.post("/api/v1/assist")
def assist(r:AssistanceRequest):
    if r.child_data:
        allowed=False; reason="p14_consent_gate_required"
    else:
        allowed=True; reason="governed_assistance_only"
    result={"request_id":r.request_id,"allowed":allowed,"reason":reason,"output_type":"assistance_envelope","suggestions":(["Summarize the supplied evidence and identify explicit gaps."] if allowed else []),"evidence_refs":r.evidence_refs,"uncertainty":"explicit","authoritative":False,"coach_final_authority":True,"autonomous_decision":False}
    audit_event("ai_assistance_request",{"request_id":r.request_id,"actor_id":r.actor_id,"actor_role":r.actor_role,"academy_id":r.academy_id,"allowed":allowed,"reason":reason,"evidence_refs":r.evidence_refs})
    return result

@app.post("/api/v1/disposition")
def disposition(r:DispositionRequest):
    audit_event("coach_ai_disposition",r.model_dump())
    return {"request_id":r.request_id,"disposition":r.disposition.value,"coach_final_authority":True,"recorded":True}

@app.get("/api/v1/audit")
def get_audit():
    return {"events":audit_log}

@app.get("/api/v1/policy")
def policy():
    return {"governed":True,"coach_final_authority":True,"autonomous_decision":False,"fabricated_evidence":False,"athlete_ranking":False,"medical_diagnosis":False,"scientific_validity_claims":False,"p13_rbac_required":True,"p14_consent_required":True,"human_review_required":True}
