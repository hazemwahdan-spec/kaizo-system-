"""Integrated state-cycle runtime for FEAT-042..045.

FEAT-042 updates the current Digital Twin state.
FEAT-043 records an immutable version/history snapshot for every update.
FEAT-044 links a decision cycle to a concrete state reference.
FEAT-045 retrieves the latest state for the next decision.

The layer is durable when PostgreSQL is enabled, memory-safe for tests/local runs,
and always preserves Coach Final Authority with execution_authorized=False.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

import persistence

router = APIRouter(prefix="/api/v1/state-cycle", tags=["state-cycle"])

_MEMORY_STATE: Dict[str, Dict[str, Any]] = {}
_MEMORY_HISTORY: List[Dict[str, Any]] = []
_MEMORY_LINKS: List[Dict[str, Any]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _authority(value: bool) -> None:
    if not value:
        raise HTTPException(status_code=409, detail="Coach Final Authority is mandatory")


def _ensure_schema() -> None:
    if not persistence.is_postgres_enabled():
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS kaizo_digital_twin_history (
                    history_id TEXT PRIMARY KEY,
                    entity_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    state JSONB NOT NULL,
                    source_event TEXT NOT NULL,
                    case_id TEXT NOT NULL,
                    recorded_by TEXT NOT NULL,
                    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
                    recorded_at TEXT NOT NULL,
                    coach_final_authority BOOLEAN NOT NULL,
                    execution_authorized BOOLEAN NOT NULL DEFAULT FALSE,
                    UNIQUE(entity_id, version)
                );
                CREATE INDEX IF NOT EXISTS idx_kaizo_digital_twin_history_entity
                    ON kaizo_digital_twin_history(entity_id, version);

                CREATE TABLE IF NOT EXISTS kaizo_decision_state_links (
                    link_id TEXT PRIMARY KEY,
                    decision_id TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    state_ref TEXT NOT NULL,
                    linked_by TEXT NOT NULL,
                    linked_at TEXT NOT NULL,
                    coach_final_authority BOOLEAN NOT NULL,
                    execution_authorized BOOLEAN NOT NULL DEFAULT FALSE
                );
                CREATE INDEX IF NOT EXISTS idx_kaizo_decision_state_links_decision
                    ON kaizo_decision_state_links(decision_id, linked_at);
                """
            )
        conn.commit()


def _get_state(entity_id: str) -> Optional[Dict[str, Any]]:
    if persistence.is_postgres_enabled():
        return persistence.get_digital_twin(entity_id)
    return _MEMORY_STATE.get(entity_id)


def _save_state(record: Dict[str, Any]) -> None:
    _MEMORY_STATE[record["entity_id"]] = record
    if persistence.is_postgres_enabled():
        persistence.upsert_digital_twin(record)


def _save_history(record: Dict[str, Any]) -> None:
    _MEMORY_HISTORY.append(record)
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kaizo_digital_twin_history
                    (history_id,entity_id,version,state,source_event,case_id,recorded_by,
                     evidence_refs,recorded_at,coach_final_authority,execution_authorized)
                    VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,%s)
                    ON CONFLICT (entity_id,version) DO NOTHING
                    """,
                    (
                        record["history_id"], record["entity_id"], record["version"],
                        __import__("json").dumps(record["state"]), record["source_event"],
                        record["case_id"], record["recorded_by"],
                        __import__("json").dumps(record["evidence_refs"]),
                        record["recorded_at"], True, False,
                    ),
                )
            conn.commit()


def _save_link(record: Dict[str, Any]) -> None:
    _MEMORY_LINKS.append(record)
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO kaizo_decision_state_links
                    (link_id,decision_id,entity_id,state_version,state_ref,linked_by,linked_at,
                     coach_final_authority,execution_authorized)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        record["link_id"], record["decision_id"], record["entity_id"],
                        record["state_version"], record["state_ref"], record["linked_by"],
                        record["linked_at"], True, False,
                    ),
                )
            conn.commit()


def _latest_link(decision_id: Optional[str] = None,
                  entity_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if decision_id:
                    cur.execute(
                        """SELECT link_id,decision_id,entity_id,state_version,state_ref,
                                  linked_by,linked_at,coach_final_authority,execution_authorized
                           FROM kaizo_decision_state_links
                           WHERE decision_id=%s ORDER BY linked_at DESC LIMIT 1""",
                        (decision_id,),
                    )
                else:
                    cur.execute(
                        """SELECT link_id,decision_id,entity_id,state_version,state_ref,
                                  linked_by,linked_at,coach_final_authority,execution_authorized
                           FROM kaizo_decision_state_links
                           WHERE entity_id=%s ORDER BY linked_at DESC LIMIT 1""",
                        (entity_id,),
                    )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "link_id": row[0], "decision_id": row[1], "entity_id": row[2],
            "state_version": row[3], "state_ref": row[4], "linked_by": row[5],
            "linked_at": row[6], "coach_final_authority": row[7],
            "execution_authorized": row[8],
        }

    candidates = [
        x for x in _MEMORY_LINKS
        if (decision_id is None or x["decision_id"] == decision_id)
        and (entity_id is None or x["entity_id"] == entity_id)
    ]
    return candidates[-1] if candidates else None


class DigitalTwinUpdateRequest(BaseModel):
    entity_id: str
    state: Dict[str, Any]
    source_event: str
    case_id: str
    updated_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    expected_version: Optional[int] = None
    coach_final_authority: bool = True


class StateLinkRequest(BaseModel):
    decision_id: str
    entity_id: str
    state_version: int
    state_ref: str
    linked_by: str
    coach_final_authority: bool = True


class NextStateRequest(BaseModel):
    athlete_id: str
    requested_by: str
    decision_id: Optional[str] = None
    coach_final_authority: bool = True


@router.post("/feat-042/digital-twin-state", status_code=status.HTTP_201_CREATED)
def update_digital_twin(req: DigitalTwinUpdateRequest) -> Dict[str, Any]:
    _authority(req.coach_final_authority)
    for name, value in (
        ("entity_id", req.entity_id), ("source_event", req.source_event),
        ("case_id", req.case_id), ("updated_by", req.updated_by)
    ):
        if not value.strip():
            raise HTTPException(400, detail=f"{name} is required")
    if not req.state:
        raise HTTPException(400, detail="state must be a non-empty object")
    if not req.evidence_refs:
        raise HTTPException(400, detail="evidence_refs are required for FEAT-042")

    current = _get_state(req.entity_id)
    current_version = int(current["version"]) if current else 0
    if req.expected_version is not None and req.expected_version != current_version:
        raise HTTPException(
            status_code=409,
            detail={"expected_version": req.expected_version, "current_version": current_version},
        )

    version = current_version + 1
    now = _now()
    state = {
        "entity_id": req.entity_id,
        "version": version,
        "state": req.state,
        "source_event": req.source_event,
        "case_id": req.case_id,
        "updated_at": now,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    history = {
        "history_id": str(uuid4()),
        "entity_id": req.entity_id,
        "version": version,
        "state": req.state,
        "source_event": req.source_event,
        "case_id": req.case_id,
        "recorded_by": req.updated_by,
        "evidence_refs": req.evidence_refs,
        "recorded_at": now,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    _save_state(state)
    _save_history(history)

    if persistence.is_postgres_enabled():
        persistence.append_audit(
            timestamp=now, who=req.updated_by, action="FEAT-042_STATE_UPDATED",
            old_value=current, new_value=state,
            why="Digital Twin state updated under Coach Final Authority; FEAT-043 history recorded.",
        )

    return {"feature_id": "FEAT-042", "state": state, "history": history}


@router.get("/feat-042/digital-twin-state/{entity_id}")
def get_digital_twin(entity_id: str) -> Dict[str, Any]:
    state = _get_state(entity_id)
    if state is None:
        raise HTTPException(404, detail="digital twin state not found")
    return state


@router.get("/feat-043/state-history/{entity_id}")
def get_state_history(entity_id: str) -> Dict[str, Any]:
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT history_id,entity_id,version,state,source_event,case_id,
                              recorded_by,evidence_refs,recorded_at,coach_final_authority,
                              execution_authorized
                       FROM kaizo_digital_twin_history
                       WHERE entity_id=%s ORDER BY version""",
                    (entity_id,),
                )
                rows = cur.fetchall()
        history = [
            {
                "history_id": r[0], "entity_id": r[1], "version": r[2], "state": r[3],
                "source_event": r[4], "case_id": r[5], "recorded_by": r[6],
                "evidence_refs": r[7], "recorded_at": r[8],
                "coach_final_authority": r[9], "execution_authorized": r[10],
            }
            for r in rows
        ]
    else:
        history = [x for x in _MEMORY_HISTORY if x["entity_id"] == entity_id]
    return {"entity_id": entity_id, "versions": history, "latest_version": history[-1]["version"] if history else None}


@router.post("/feat-044/decision-state-link", status_code=status.HTTP_201_CREATED)
def link_decision_to_state(req: StateLinkRequest) -> Dict[str, Any]:
    _authority(req.coach_final_authority)
    for name, value in (
        ("decision_id", req.decision_id), ("entity_id", req.entity_id),
        ("state_ref", req.state_ref), ("linked_by", req.linked_by)
    ):
        if not value.strip():
            raise HTTPException(400, detail=f"{name} is required")
    if req.state_version < 1:
        raise HTTPException(400, detail="state_version must be >= 1")

    current = _get_state(req.entity_id)
    if current is None:
        raise HTTPException(404, detail="digital twin state not found")
    if int(current["version"]) != req.state_version:
        raise HTTPException(
            409,
            detail={"state_version": req.state_version, "current_version": current["version"],
                    "reason": "state_ref must point to the current retrievable state"},
        )

    expected_ref = f"{req.entity_id}:v{req.state_version}"
    if req.state_ref != expected_ref:
        raise HTTPException(400, detail={"expected_state_ref": expected_ref})

    record = {
        "link_id": str(uuid4()), "decision_id": req.decision_id,
        "entity_id": req.entity_id, "state_version": req.state_version,
        "state_ref": req.state_ref, "linked_by": req.linked_by,
        "linked_at": _now(), "coach_final_authority": True,
        "execution_authorized": False,
    }
    _save_link(record)
    if persistence.is_postgres_enabled():
        persistence.append_audit(
            timestamp=record["linked_at"], who=req.linked_by,
            action="FEAT-044_DECISION_STATE_LINKED", old_value=None, new_value=record,
            why="Decision cycle linked to an explicit Digital Twin state version.",
        )
    return {"feature_id": "FEAT-044", "link": record}


@router.get("/feat-044/decision-state-link/{decision_id}")
def get_decision_state_link(decision_id: str) -> Dict[str, Any]:
    link = _latest_link(decision_id=decision_id)
    if link is None:
        raise HTTPException(404, detail="decision-state link not found")
    return link


@router.post("/feat-045/next-state", status_code=status.HTTP_200_OK)
def retrieve_next_state(req: NextStateRequest) -> Dict[str, Any]:
    _authority(req.coach_final_authority)
    if not req.athlete_id.strip() or not req.requested_by.strip():
        raise HTTPException(400, detail="athlete_id and requested_by are required")

    state = _get_state(req.athlete_id)
    if state is None:
        raise HTTPException(404, detail="no Digital Twin state available for athlete")

    link = _latest_link(decision_id=req.decision_id, entity_id=req.athlete_id)
    now = _now()
    result = {
        "feature_id": "FEAT-045",
        "athlete_id": req.athlete_id,
        "requested_by": req.requested_by,
        "retrieved_at": now,
        "state": state,
        "linked_decision_state": link,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    if persistence.is_postgres_enabled():
        persistence.append_audit(
            timestamp=now, who=req.requested_by, action="FEAT-045_NEXT_STATE_RETRIEVED",
            old_value=None, new_value=result,
            why="Latest Digital Twin state retrieved as input to the next decision; no autonomous execution.",
        )
    return result
