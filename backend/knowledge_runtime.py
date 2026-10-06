"""Dedicated knowledge runtime for FEAT-047..050.
Quality gate: provenance, lifecycle, retrieval context, and reusable-unit linkage.
Coach Final Authority is mandatory; execution authorization is always false.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import persistence

router=APIRouter(prefix="/api/v1/knowledge-runtime",tags=["Knowledge Runtime"])
MEMORY_ITEMS:Dict[str,Dict[str,Any]]={}
MEMORY_LINKS:List[Dict[str,Any]]=[]

def now(): return datetime.now(timezone.utc).isoformat()
def authority(ok:bool):
    if not ok: raise HTTPException(409,"Coach Final Authority is mandatory")
def schema():
    if not persistence.is_postgres_enabled(): return
    with persistence.connection() as c:
        with c.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS kaizo_knowledge_provenance (
                knowledge_id TEXT PRIMARY KEY, source_type TEXT NOT NULL, source_ref TEXT NOT NULL,
                provenance_note TEXT NOT NULL, evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
                lifecycle_status TEXT NOT NULL, changed_by TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS kaizo_knowledge_unit_links (
                link_id TEXT PRIMARY KEY, knowledge_id TEXT NOT NULL, unit_id TEXT NOT NULL,
                link_type TEXT NOT NULL, evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
                linked_by TEXT NOT NULL, linked_at TEXT NOT NULL);""")
        c.commit()

def save_item(r):
    MEMORY_ITEMS[r["knowledge_id"]]=r
    if persistence.is_postgres_enabled():
        schema()
        persistence.upsert_knowledge(r["knowledge_id"],r, r["updated_at"])
        persistence.append_audit(timestamp=r["updated_at"],who=r["changed_by"],action="FEAT-047_048_KNOWLEDGE_RECORDED",old_value=None,new_value=r,why="Knowledge retained with provenance and lifecycle metadata.")

def get_item(k):
    if persistence.is_postgres_enabled():
        data=persistence.load_knowledge().get(k)
        if data: return data
    return MEMORY_ITEMS.get(k)

class ProvenanceRequest(BaseModel):
    knowledge_id:str; source_type:str; source_ref:str; provenance_note:str
    evidence_refs:List[str]=Field(default_factory=list); changed_by:str
    coach_final_authority:bool=True

class LifecycleRequest(BaseModel):
    knowledge_id:str; lifecycle_status:str; changed_by:str
    coach_final_authority:bool=True

class RetrievalRequest(BaseModel):
    workflow_context:str; query:str; requested_by:str; coach_final_authority:bool=True

class LinkRequest(BaseModel):
    knowledge_id:str; unit_id:str; link_type:str; linked_by:str
    evidence_refs:List[str]=Field(default_factory=list); coach_final_authority:bool=True

@router.post("/feat-047/provenance",status_code=201)
def provenance(req:ProvenanceRequest):
    authority(req.coach_final_authority)
    if not req.knowledge_id.strip() or not req.source_type.strip() or not req.source_ref.strip() or not req.provenance_note.strip() or not req.changed_by.strip():
        raise HTTPException(400,"knowledge_id, source_type, source_ref, provenance_note and changed_by are required")
    if not req.evidence_refs: raise HTTPException(400,"at least one evidence reference is required")
    r={"knowledge_id":req.knowledge_id,"source_type":req.source_type,"source_ref":req.source_ref,
       "provenance_note":req.provenance_note,"evidence_refs":req.evidence_refs,"lifecycle_status":"DRAFT",
       "changed_by":req.changed_by,"created_at":now(),"updated_at":now(),"coach_final_authority":True,"execution_authorized":False}
    save_item(r); return {"feature_id":"FEAT-047","record":r}

@router.post("/feat-048/lifecycle",status_code=200)
def lifecycle(req:LifecycleRequest):
    authority(req.coach_final_authority)
    allowed={"DRAFT","REVIEW","APPROVED","RETIRED","REJECTED"}
    if req.lifecycle_status not in allowed: raise HTTPException(400,{"allowed":sorted(allowed)})
    r=get_item(req.knowledge_id)
    if not r: raise HTTPException(404,"knowledge item not found")
    old=r["lifecycle_status"]; r=dict(r); r["lifecycle_status"]=req.lifecycle_status; r["changed_by"]=req.changed_by; r["updated_at"]=now()
    save_item(r)
    return {"feature_id":"FEAT-048","previous_status":old,"record":r}

@router.post("/feat-049/retrieve",status_code=200)
def retrieve(req:RetrievalRequest):
    authority(req.coach_final_authority)
    if not req.workflow_context.strip() or not req.query.strip() or not req.requested_by.strip(): raise HTTPException(400,"workflow_context, query and requested_by are required")
    q=req.query.lower()
    candidates=[r for r in MEMORY_ITEMS.values() if r["lifecycle_status"]=="APPROVED" and (q in r["knowledge_id"].lower() or q in r["provenance_note"].lower() or q in r["source_ref"].lower())]
    if persistence.is_postgres_enabled():
        for r in persistence.load_knowledge().values():
            if r.get("lifecycle_status")=="APPROVED" and (q in r.get("knowledge_id","").lower() or q in r.get("provenance_note","").lower() or q in r.get("source_ref","").lower()):
                if not any(x.get("knowledge_id")==r.get("knowledge_id") for x in candidates): candidates.append(r)
    return {"feature_id":"FEAT-049","workflow_context":req.workflow_context,"query":req.query,"results":candidates,"retrieved_by":req.requested_by,"coach_final_authority":True,"execution_authorized":False}

@router.post("/feat-050/link",status_code=201)
def link(req:LinkRequest):
    authority(req.coach_final_authority)
    r=get_item(req.knowledge_id)
    if not r: raise HTTPException(404,"knowledge item not found")
    if r["lifecycle_status"]!="APPROVED": raise HTTPException(409,"knowledge must be APPROVED before reusable linkage")
    if not req.unit_id.strip() or not req.link_type.strip() or not req.linked_by.strip(): raise HTTPException(400,"unit_id, link_type and linked_by are required")
    if not req.evidence_refs: raise HTTPException(400,"at least one evidence reference is required")
    out={"link_id":str(uuid4()),"knowledge_id":req.knowledge_id,"unit_id":req.unit_id,"link_type":req.link_type,
         "evidence_refs":req.evidence_refs,"linked_by":req.linked_by,"linked_at":now(),"coach_final_authority":True,"execution_authorized":False}
    MEMORY_LINKS.append(out)
    if persistence.is_postgres_enabled():
        schema()
        with persistence.connection() as c:
            with c.cursor() as cur:
                import json
                cur.execute("INSERT INTO kaizo_knowledge_unit_links(link_id,knowledge_id,unit_id,link_type,evidence_refs,linked_by,linked_at) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)",(out["link_id"],out["knowledge_id"],out["unit_id"],out["link_type"],json.dumps(out["evidence_refs"]),out["linked_by"],out["linked_at"]))
            c.commit()
        persistence.append_audit(timestamp=out["linked_at"],who=req.linked_by,action="FEAT-050_KNOWLEDGE_UNIT_LINKED",old_value=None,new_value=out,why="Approved knowledge linked to reusable unit with evidence.")
    return {"feature_id":"FEAT-050","link":out}
