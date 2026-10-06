"""KAIZO audit/trace runtime for FEAT-052..055.
Quality gate: actor/action/time trace, governance metadata, audit review,
and product-action traceability. Coach Final Authority is mandatory;
execution authorization is permanently false.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import persistence

router=APIRouter(prefix="/api/v1/audit-trace",tags=["Audit Trace"])
MEMORY_EVENTS:List[Dict[str,Any]]=[]
MEMORY_GOVERNANCE:Dict[str,Dict[str,Any]]={}
MEMORY_LINKS:List[Dict[str,Any]]=[]

def now(): return datetime.now(timezone.utc).isoformat()
def authority(ok:bool):
    if not ok: raise HTTPException(409,"Coach Final Authority is mandatory")

def schema():
    if not persistence.is_postgres_enabled(): return
    with persistence.connection() as c:
        with c.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS kaizo_actor_action_trace (
                trace_id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, action TEXT NOT NULL,
                occurred_at TEXT NOT NULL, evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
                coach_final_authority BOOLEAN NOT NULL, execution_authorized BOOLEAN NOT NULL);
            CREATE TABLE IF NOT EXISTS kaizo_governance_metadata (
                object_id TEXT PRIMARY KEY, object_type TEXT NOT NULL, governance_status TEXT NOT NULL,
                owner TEXT NOT NULL, metadata JSONB NOT NULL DEFAULT '{}'::jsonb, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS kaizo_product_action_trace (
                trace_id TEXT PRIMARY KEY, product_action TEXT NOT NULL,
                source_record_ids JSONB NOT NULL, trace_reason TEXT NOT NULL,
                traced_by TEXT NOT NULL, traced_at TEXT NOT NULL);""")
        c.commit()

class ActorTraceRequest(BaseModel):
    actor_id:str; action:str; occurred_at:str=""; evidence_refs:List[str]=Field(default_factory=list)
    coach_final_authority:bool=True

class GovernanceRequest(BaseModel):
    object_id:str; object_type:str; governance_status:str; owner:str
    metadata:Dict[str,Any]=Field(default_factory=dict); coach_final_authority:bool=True

class AuditReviewRequest(BaseModel):
    query:str; reviewed_by:str; coach_final_authority:bool=True

class ProductTraceRequest(BaseModel):
    product_action:str; source_record_ids:List[str]; trace_reason:str; traced_by:str
    coach_final_authority:bool=True

def save_trace(r):
    MEMORY_EVENTS.append(r)
    if persistence.is_postgres_enabled():
        schema()
        with persistence.connection() as c:
            with c.cursor() as cur:
                import json
                cur.execute("INSERT INTO kaizo_actor_action_trace(trace_id,actor_id,action,occurred_at,evidence_refs,coach_final_authority,execution_authorized) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)",
                    (r["trace_id"],r["actor_id"],r["action"],r["occurred_at"],json.dumps(r["evidence_refs"]),True,False))
            c.commit()
        persistence.append_audit(timestamp=r["occurred_at"],who=r["actor_id"],action="FEAT-052_ACTOR_ACTION_TRACED",old_value=None,new_value=r,why="Actor/action/time trace retained.")

@router.post("/feat-052/trace",status_code=201)
def trace(req:ActorTraceRequest):
    authority(req.coach_final_authority)
    if not req.actor_id.strip() or not req.action.strip(): raise HTTPException(400,"actor_id and action are required")
    occurred=req.occurred_at.strip() or now()
    r={"feature_id":"FEAT-052","trace_id":str(uuid4()),"actor_id":req.actor_id,"action":req.action,
       "occurred_at":occurred,"evidence_refs":req.evidence_refs,"coach_final_authority":True,"execution_authorized":False}
    save_trace(r); return r

@router.post("/feat-053/governance",status_code=201)
def governance(req:GovernanceRequest):
    authority(req.coach_final_authority)
    if not req.object_id.strip() or not req.object_type.strip() or not req.governance_status.strip() or not req.owner.strip():
        raise HTTPException(400,"object_id, object_type, governance_status and owner are required")
    r={"feature_id":"FEAT-053","object_id":req.object_id,"object_type":req.object_type,
       "governance_status":req.governance_status,"owner":req.owner,"metadata":req.metadata,
       "updated_at":now(),"coach_final_authority":True,"execution_authorized":False}
    MEMORY_GOVERNANCE[req.object_id]=r
    if persistence.is_postgres_enabled():
        schema()
        with persistence.connection() as c:
            with c.cursor() as cur:
                import json
                cur.execute("INSERT INTO kaizo_governance_metadata(object_id,object_type,governance_status,owner,metadata,updated_at) VALUES (%s,%s,%s,%s,%s::jsonb,%s) ON CONFLICT(object_id) DO UPDATE SET object_type=EXCLUDED.object_type,governance_status=EXCLUDED.governance_status,owner=EXCLUDED.owner,metadata=EXCLUDED.metadata,updated_at=EXCLUDED.updated_at",
                    (r["object_id"],r["object_type"],r["governance_status"],r["owner"],json.dumps(r["metadata"]),r["updated_at"]))
            c.commit()
    return r

@router.post("/feat-054/review",status_code=200)
def review(req:AuditReviewRequest):
    authority(req.coach_final_authority)
    if not req.query.strip() or not req.reviewed_by.strip(): raise HTTPException(400,"query and reviewed_by are required")
    q=req.query.lower()
    results=[r for r in MEMORY_EVENTS if q in str(r).lower()]
    results += [r for r in MEMORY_GOVERNANCE.values() if q in str(r).lower() and r not in results]
    if persistence.is_postgres_enabled():
        try:
            data=persistence.load_knowledge()
            results += [r for r in data.values() if q in str(r).lower()]
        except Exception:
            pass
    return {"feature_id":"FEAT-054","query":req.query,"reviewed_by":req.reviewed_by,"results":results,
            "reviewed_at":now(),"coach_final_authority":True,"execution_authorized":False}

@router.post("/feat-055/trace",status_code=201)
def product_trace(req:ProductTraceRequest):
    authority(req.coach_final_authority)
    if not req.product_action.strip() or not req.traced_by.strip() or not req.trace_reason.strip():
        raise HTTPException(400,"product_action, source_record_ids and trace_reason are required")
    if not req.source_record_ids: raise HTTPException(400,"source_record_ids must be a non-empty list")
    r={"feature_id":"FEAT-055","trace_id":str(uuid4()),"product_action":req.product_action,
       "source_record_ids":req.source_record_ids,"trace_reason":req.trace_reason,"traced_by":req.traced_by,
       "traced_at":now(),"coach_final_authority":True,"execution_authorized":False}
    MEMORY_LINKS.append(r)
    if persistence.is_postgres_enabled():
        schema()
        with persistence.connection() as c:
            with c.cursor() as cur:
                import json
                cur.execute("INSERT INTO kaizo_product_action_trace(trace_id,product_action,source_record_ids,trace_reason,traced_by,traced_at) VALUES (%s,%s,%s::jsonb,%s,%s,%s)",
                    (r["trace_id"],r["product_action"],json.dumps(r["source_record_ids"]),r["trace_reason"],r["traced_by"],r["traced_at"]))
            c.commit()
        persistence.append_audit(timestamp=r["traced_at"],who=req.traced_by,action="FEAT-055_PRODUCT_ACTION_TRACED",old_value=None,new_value=r,why="Product action linked to source records.")
    return r
