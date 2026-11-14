"""Ownership-scoped, auditable Digital Twin state cycle (FEAT-042..045)."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
import json

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

import persistence
from productization import coach_roster
from productization.product_api import verified_coach_scope

router = APIRouter(prefix="/api/v1/state-cycle", tags=["state-cycle"])
_MEMORY_STATE: Dict[tuple[str, str, str], Dict[str, Any]] = {}
_MEMORY_HISTORY: List[Dict[str, Any]] = []
_MEMORY_LINKS: List[Dict[str, Any]] = []
_MEMORY_AUDIT: List[Dict[str, Any]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema() -> None:
    """Compatibility hook; canonical schema is provisioned by persistence.initialize()."""
    if persistence.is_postgres_enabled():
        persistence.initialize()


def _principal(authorization, actor_id, role, tenant_id, owner, athlete_id):
    principal = verified_coach_scope(authorization, actor_id, role, tenant_id, owner)
    if principal.verified and not persistence.is_postgres_enabled():
        raise HTTPException(
            503, detail="verified Coach Digital Twin routes require durable PostgreSQL"
        )
    athlete = coach_roster.get_owned_athlete(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id,
    )
    if athlete is None:
        raise HTTPException(404, detail="athlete not found in Coach scope")
    return principal


def _auth_headers(authorization, actor_id, role, tenant_id, owner, athlete_id):
    return _principal(authorization, actor_id, role, tenant_id, owner, athlete_id)


def _scope_check(cur, athlete_id, principal):
    cur.execute(
        """SELECT 1 FROM kaizo_coach_athlete_ownership
           WHERE athlete_id=%s AND tenant_id=%s AND coach_actor_id=%s
           FOR KEY SHARE""",
        (athlete_id, principal.tenant_id, principal.actor_id),
    )
    if cur.fetchone() is None:
        raise HTTPException(404, detail="athlete not found in Coach scope")


def _verified_athlete_evidence(cur, athlete_id: str, evidence_refs: List[str]) -> None:
    """Lock only VERIFIED, non-E0 evidence belonging to this exact athlete."""
    refs = [str(item).strip() for item in evidence_refs]
    if (not refs or any(not item for item in refs)
            or len(refs) != len(set(refs))):
        raise HTTPException(409, detail="FEAT-042 evidence_refs must be non-empty and unique")
    cur.execute(
        """SELECT evidence_id,evidence_level,status
           FROM kaizo_evidence_records
           WHERE evidence_id=ANY(%s)
             AND LOWER(subject_type)='athlete' AND subject_id=%s
           FOR SHARE""",
        (refs, athlete_id),
    )
    valid = {
        str(row[0]) for row in cur.fetchall()
        if str(row[1] or "").strip().upper() != "E0"
        and str(row[2] or "").strip().upper() == "VERIFIED"
    }
    if valid != set(refs):
        raise HTTPException(
            409,
            detail="FEAT-042 requires VERIFIED, non-E0 evidence records scoped to the same athlete",
        )


def _get_state(athlete_id: str, principal: Any) -> Optional[Dict[str, Any]]:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                # Recheck and lock current ownership in the same transaction
                # as the read so a concurrent transfer cannot expose stale data.
                _scope_check(cur, athlete_id, principal)
                cur.execute(
                    """SELECT entity_id,version,state,source_event,case_id,updated_at,
                              tenant_id,coach_actor_id
                       FROM kaizo_digital_twin_state
                       WHERE entity_id=%s AND tenant_id=%s AND coach_actor_id=%s""",
                    (athlete_id, principal.tenant_id, principal.actor_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"entity_id":row[0],"version":row[1],"state":row[2],
                "source_event":row[3],"case_id":row[4],"updated_at":row[5],
                "tenant_id":row[6],"coach_actor_id":row[7]}
    return _MEMORY_STATE.get((principal.tenant_id, principal.actor_id, athlete_id))


def _persist_update(state: Dict[str, Any], history: Dict[str, Any],
                    old_state: Optional[Dict[str, Any]], principal: Any) -> None:
    if not persistence.is_postgres_enabled():
        key=(principal.tenant_id,principal.actor_id,state["entity_id"])
        _MEMORY_STATE[key]=state
        _MEMORY_HISTORY.append(history)
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            _scope_check(cur,state["entity_id"],principal)
            # Evidence locks, state version, history and tenant audit share this
            # transaction; no caller-supplied or cross-athlete evidence survives.
            _verified_athlete_evidence(cur, state["entity_id"], history["evidence_refs"])
            cur.execute(
                """SELECT version,tenant_id,coach_actor_id FROM kaizo_digital_twin_state
                   WHERE entity_id=%s FOR UPDATE""",(state["entity_id"],))
            existing=cur.fetchone()
            if existing and (existing[1] != principal.tenant_id or existing[2] != principal.actor_id):
                raise HTTPException(409,detail="legacy or differently scoped Digital Twin state requires provenance review")
            if existing and int(existing[0]) != int(state["version"])-1:
                raise HTTPException(409,detail="Digital Twin version changed; reload before retrying")
            if not existing and int(state["version"]) != 1:
                raise HTTPException(409,detail="Digital Twin state must begin at version 1")
            cur.execute(
                """INSERT INTO kaizo_digital_twin_state
                   (entity_id,version,state,source_event,case_id,updated_at,tenant_id,coach_actor_id)
                   VALUES (%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
                   ON CONFLICT(entity_id) DO UPDATE SET
                     version=EXCLUDED.version,state=EXCLUDED.state,
                     source_event=EXCLUDED.source_event,case_id=EXCLUDED.case_id,
                     updated_at=EXCLUDED.updated_at
                   WHERE kaizo_digital_twin_state.tenant_id=EXCLUDED.tenant_id
                     AND kaizo_digital_twin_state.coach_actor_id=EXCLUDED.coach_actor_id
                     AND kaizo_digital_twin_state.version=EXCLUDED.version-1""",
                (state["entity_id"],state["version"],json.dumps(state["state"]),
                 state["source_event"],state["case_id"],state["updated_at"],
                 principal.tenant_id,principal.actor_id))
            cur.execute(
                """INSERT INTO kaizo_digital_twin_history
                   (history_id,entity_id,version,state,source_event,case_id,recorded_by,
                    evidence_refs,recorded_at,coach_final_authority,execution_authorized,
                    tenant_id,coach_actor_id)
                   VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,TRUE,FALSE,%s,%s)""",
                (history["history_id"],history["entity_id"],history["version"],
                 json.dumps(history["state"]),history["source_event"],history["case_id"],
                 principal.actor_id,json.dumps(history["evidence_refs"]),
                 history["recorded_at"],principal.tenant_id,principal.actor_id))
            cur.execute(
                """INSERT INTO kaizo_audit_logs
                   (timestamp,who,action,old_value,new_value,why,tenant_id)
                   VALUES (%s,%s,'FEAT-042_STATE_UPDATED',%s::jsonb,%s::jsonb,%s,%s)""",
                (state["updated_at"],principal.actor_id,json.dumps(old_state),
                 json.dumps(state),"Digital Twin state/history committed atomically under verified Coach ownership.",
                 principal.tenant_id))
        conn.commit()


def _save_link(record: Dict[str, Any], principal: Any) -> None:
    if not persistence.is_postgres_enabled():
        _MEMORY_LINKS.append(record)
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            _scope_check(cur,record["entity_id"],principal)
            cur.execute(
                """SELECT 1 FROM kaizo_digital_twin_state
                   WHERE entity_id=%s AND version=%s AND tenant_id=%s AND coach_actor_id=%s
                   FOR KEY SHARE""",
                (record["entity_id"],record["state_version"],principal.tenant_id,principal.actor_id))
            if cur.fetchone() is None:
                raise HTTPException(404,detail="scoped Digital Twin state version not found")
            cur.execute(
                """INSERT INTO kaizo_decision_state_links
                   (link_id,decision_id,entity_id,state_version,state_ref,linked_by,linked_at,
                    coach_final_authority,execution_authorized,tenant_id,coach_actor_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,FALSE,%s,%s)""",
                (record["link_id"],record["decision_id"],record["entity_id"],
                 record["state_version"],record["state_ref"],principal.actor_id,
                 record["linked_at"],principal.tenant_id,principal.actor_id))
            cur.execute(
                """INSERT INTO kaizo_audit_logs
                   (timestamp,who,action,old_value,new_value,why,tenant_id)
                   VALUES (%s,%s,'FEAT-044_DECISION_STATE_LINKED',NULL,%s::jsonb,%s,%s)""",
                (record["linked_at"],principal.actor_id,json.dumps(record),
                 "Decision linked to an owned, versioned Digital Twin state.",
                 principal.tenant_id))
        conn.commit()


def _latest_link(decision_id: Optional[str], athlete_id: str, principal: Any):
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                _scope_check(cur, athlete_id, principal)
                cur.execute(
                    """SELECT link_id,decision_id,entity_id,state_version,state_ref,
                              linked_by,linked_at,coach_final_authority,execution_authorized
                       FROM kaizo_decision_state_links
                       WHERE entity_id=%s AND tenant_id=%s AND coach_actor_id=%s
                         AND (%s IS NULL OR decision_id=%s)
                       ORDER BY linked_at DESC LIMIT 1""",
                    (athlete_id,principal.tenant_id,principal.actor_id,decision_id,decision_id))
                r=cur.fetchone()
        if r is None: return None
        return {"link_id":r[0],"decision_id":r[1],"entity_id":r[2],"state_version":r[3],
                "state_ref":r[4],"linked_by":r[5],"linked_at":r[6],
                "coach_final_authority":r[7],"execution_authorized":r[8]}
    items=[x for x in _MEMORY_LINKS if x["entity_id"]==athlete_id
           and x["tenant_id"]==principal.tenant_id and x["coach_actor_id"]==principal.actor_id
           and (decision_id is None or x["decision_id"]==decision_id)]
    return items[-1] if items else None


class DigitalTwinUpdateRequest(BaseModel):
    entity_id: str
    state: Dict[str, Any]
    source_event: str
    case_id: str
    evidence_refs: List[str] = Field(min_length=1)
    expected_version: Optional[int] = None
    coach_final_authority: bool = True


class StateLinkRequest(BaseModel):
    decision_id: str
    entity_id: str
    state_version: int
    state_ref: str
    coach_final_authority: bool = True


class NextStateRequest(BaseModel):
    athlete_id: str
    decision_id: Optional[str] = None
    coach_final_authority: bool = True


def _authority(value: bool):
    if not value:
        raise HTTPException(409,detail="Coach Final Authority is mandatory")


def _common_headers(authorization, actor_id, role, tenant_id, owner, athlete_id):
    return _auth_headers(authorization,actor_id,role,tenant_id,owner,athlete_id)


@router.post("/feat-042/digital-twin-state",status_code=status.HTTP_201_CREATED)
def update_digital_twin(req: DigitalTwinUpdateRequest,
    authorization: str|None=Header(None,alias="Authorization"),
    actor_id: str|None=Header(None,alias="X-KAIZO-Actor"),
    role: str|None=Header(None,alias="X-KAIZO-Role"),
    tenant_id: str|None=Header(None,alias="X-KAIZO-Tenant"),
    owner: str|None=Header(None,alias="X-KAIZO-Resource-Owner")):
    principal=_common_headers(authorization,actor_id,role,tenant_id,owner,req.entity_id)
    _authority(req.coach_final_authority)
    if not req.state or not req.source_event.strip() or not req.case_id.strip():
        raise HTTPException(400,detail="state, source_event and case_id are required")
    current=_get_state(req.entity_id,principal)
    version=int(current["version"]) if current else 0
    if req.expected_version is not None and req.expected_version != version:
        raise HTTPException(409,detail={"expected_version":req.expected_version,"current_version":version})
    now=_now()
    state={"entity_id":req.entity_id,"version":version+1,"state":req.state,
           "source_event":req.source_event,"case_id":req.case_id,"updated_at":now,
           "tenant_id":principal.tenant_id,"coach_actor_id":principal.actor_id,
           "coach_final_authority":True,"execution_authorized":False}
    history={"history_id":str(uuid4()),"entity_id":req.entity_id,"version":version+1,
             "state":req.state,"source_event":req.source_event,"case_id":req.case_id,
             "recorded_by":principal.actor_id,"evidence_refs":req.evidence_refs,
             "recorded_at":now,"tenant_id":principal.tenant_id,
             "coach_actor_id":principal.actor_id,"coach_final_authority":True,
             "execution_authorized":False}
    _persist_update(state,history,current,principal)
    return {"feature_id":"FEAT-042","state":state,"history":history}


@router.get("/feat-042/digital-twin-state/{entity_id}")
def get_digital_twin(entity_id: str,
    authorization: str|None=Header(None,alias="Authorization"),
    actor_id: str|None=Header(None,alias="X-KAIZO-Actor"),
    role: str|None=Header(None,alias="X-KAIZO-Role"),
    tenant_id: str|None=Header(None,alias="X-KAIZO-Tenant"),
    owner: str|None=Header(None,alias="X-KAIZO-Resource-Owner")):
    principal=_common_headers(authorization,actor_id,role,tenant_id,owner,entity_id)
    state=_get_state(entity_id,principal)
    if state is None: raise HTTPException(404,detail="Digital Twin state not found in Coach scope")
    return state


@router.get("/feat-043/state-history/{entity_id}")
def get_state_history(entity_id: str,
    authorization: str|None=Header(None,alias="Authorization"),
    actor_id: str|None=Header(None,alias="X-KAIZO-Actor"),
    role: str|None=Header(None,alias="X-KAIZO-Role"),
    tenant_id: str|None=Header(None,alias="X-KAIZO-Tenant"),
    owner: str|None=Header(None,alias="X-KAIZO-Resource-Owner")):
    principal=_common_headers(authorization,actor_id,role,tenant_id,owner,entity_id)
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                _scope_check(cur, entity_id, principal)
                cur.execute(
                    """SELECT history_id,entity_id,version,state,source_event,case_id,
                              recorded_by,evidence_refs,recorded_at,coach_final_authority,
                              execution_authorized,tenant_id,coach_actor_id
                       FROM kaizo_digital_twin_history
                       WHERE entity_id=%s AND tenant_id=%s AND coach_actor_id=%s ORDER BY version""",
                    (entity_id,principal.tenant_id,principal.actor_id))
                rows=cur.fetchall()
        history=[{"history_id":r[0],"entity_id":r[1],"version":r[2],"state":r[3],
                  "source_event":r[4],"case_id":r[5],"recorded_by":r[6],
                  "evidence_refs":r[7],"recorded_at":r[8],"coach_final_authority":r[9],
                  "execution_authorized":r[10],"tenant_id":r[11],"coach_actor_id":r[12]} for r in rows]
    else:
        history=[x for x in _MEMORY_HISTORY if x["entity_id"]==entity_id
                 and x["tenant_id"]==principal.tenant_id and x["coach_actor_id"]==principal.actor_id]
    return {"entity_id":entity_id,"versions":history,
            "latest_version":history[-1]["version"] if history else None}


@router.post("/feat-044/decision-state-link",status_code=status.HTTP_201_CREATED)
def link_decision_to_state(req: StateLinkRequest,
    authorization: str|None=Header(None,alias="Authorization"),
    actor_id: str|None=Header(None,alias="X-KAIZO-Actor"),
    role: str|None=Header(None,alias="X-KAIZO-Role"),
    tenant_id: str|None=Header(None,alias="X-KAIZO-Tenant"),
    owner: str|None=Header(None,alias="X-KAIZO-Resource-Owner")):
    principal=_common_headers(authorization,actor_id,role,tenant_id,owner,req.entity_id)
    _authority(req.coach_final_authority)
    if not req.decision_id.strip() or req.state_version<1:
        raise HTTPException(400,detail="decision_id and a positive state_version are required")
    state=_get_state(req.entity_id,principal)
    if state is None: raise HTTPException(404,detail="Digital Twin state not found in Coach scope")
    if int(state["version"])!=req.state_version:
        raise HTTPException(409,detail={"state_version":req.state_version,"current_version":state["version"]})
    expected=f"{req.entity_id}:v{req.state_version}"
    if req.state_ref != expected: raise HTTPException(400,detail={"expected_state_ref":expected})
    now=_now()
    record={"link_id":str(uuid4()),"decision_id":req.decision_id,"entity_id":req.entity_id,
            "state_version":req.state_version,"state_ref":req.state_ref,
            "linked_by":principal.actor_id,"linked_at":now,"tenant_id":principal.tenant_id,
            "coach_actor_id":principal.actor_id,"coach_final_authority":True,
            "execution_authorized":False}
    _save_link(record,principal)
    return {"feature_id":"FEAT-044","link":record}


@router.get("/feat-044/decision-state-link/{decision_id}")
def get_decision_state_link(decision_id: str, athlete_id: str,
    authorization: str|None=Header(None,alias="Authorization"),
    actor_id: str|None=Header(None,alias="X-KAIZO-Actor"),
    role: str|None=Header(None,alias="X-KAIZO-Role"),
    tenant_id: str|None=Header(None,alias="X-KAIZO-Tenant"),
    owner: str|None=Header(None,alias="X-KAIZO-Resource-Owner")):
    principal=_common_headers(authorization,actor_id,role,tenant_id,owner,athlete_id)
    link=_latest_link(decision_id,athlete_id,principal)
    if link is None: raise HTTPException(404,detail="decision-state link not found in Coach scope")
    return link


@router.post("/feat-045/next-state")
def retrieve_next_state(req: NextStateRequest,
    authorization: str|None=Header(None,alias="Authorization"),
    actor_id: str|None=Header(None,alias="X-KAIZO-Actor"),
    role: str|None=Header(None,alias="X-KAIZO-Role"),
    tenant_id: str|None=Header(None,alias="X-KAIZO-Tenant"),
    owner: str|None=Header(None,alias="X-KAIZO-Resource-Owner")):
    principal=_common_headers(authorization,actor_id,role,tenant_id,owner,req.athlete_id)
    _authority(req.coach_final_authority)
    state=_get_state(req.athlete_id,principal)
    if state is None: raise HTTPException(404,detail="no Digital Twin state in Coach scope")
    link=_latest_link(req.decision_id,req.athlete_id,principal)
    result={"feature_id":"FEAT-045","athlete_id":req.athlete_id,"retrieved_at":_now(),
            "state":state,"linked_decision_state":link,"coach_actor_id":principal.actor_id,
            "tenant_id":principal.tenant_id,"coach_final_authority":True,"execution_authorized":False}
    audit={"timestamp":result["retrieved_at"],"who":principal.actor_id,
           "action":"FEAT-045_NEXT_STATE_RETRIEVED","old_value":None,"new_value":result,
           "why":"Latest owned Digital Twin state retrieved as input to the next Coach decision; no autonomous execution.",
           "tenant_id":principal.tenant_id}
    if persistence.is_postgres_enabled():
        persistence.append_tenant_audit(**audit)
    else:
        _MEMORY_AUDIT.append(audit)
    return result


def reset_memory_state():
    _MEMORY_STATE.clear()
    _MEMORY_HISTORY.clear()
    _MEMORY_LINKS.clear()
    _MEMORY_AUDIT.clear()
