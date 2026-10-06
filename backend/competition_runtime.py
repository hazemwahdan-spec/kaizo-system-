"""KAIZO Competition Runtime — FEAT-066..070.

Competition context is recorded as evidence-backed operational data.
Readiness and trend indicators are derived, never silently converted into
autonomous decisions. Coach Final Authority remains mandatory.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import persistence

router = APIRouter(prefix="/api/v1/competition", tags=["Competition Runtime"])

EVENTS: Dict[str, Dict[str, Any]] = {}
READINESS: Dict[str, Dict[str, Any]] = {}
PERFORMANCES: Dict[str, Dict[str, Any]] = {}
DECISIONS: Dict[str, Dict[str, Any]] = {}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def audit(actor: str, action: str, payload: Dict[str, Any]) -> None:
    if persistence.is_postgres_enabled():
        try:
            persistence.append_audit({
                "actor_id": actor, "action": action, "occurred_at": now(),
                "payload": payload, "evidence_refs": payload.get("evidence_refs", []),
                "coach_final_authority": True, "execution_authorized": False,
            })
        except Exception:
            pass


def authority(ok: bool) -> None:
    if not ok:
        raise HTTPException(status_code=409, detail="COACH_FINAL_AUTHORITY_REQUIRED")


def text_required(**values: str) -> None:
    for key, value in values.items():
        if not value or not value.strip():
            raise HTTPException(status_code=400, detail=f"{key} is required")


class EventCreate(BaseModel):
    event_name: str
    date: str
    context: Dict[str, Any]
    created_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class ReadinessCreate(BaseModel):
    athlete_id: str
    event_id: str
    indicators: Dict[str, Any]
    assessed_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class PerformanceCreate(BaseModel):
    athlete_id: str
    event_id: str
    performance: Dict[str, Any]
    recorded_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


class DecisionCreate(BaseModel):
    athlete_id: str
    event_id: str
    decision_basis: Dict[str, Any]
    decision: Dict[str, Any]
    decided_by: str
    evidence_refs: List[str] = Field(default_factory=list)
    coach_final_authority: bool = True


def _event(event_id: str) -> Dict[str, Any]:
    item = EVENTS.get(event_id)
    if item is None:
        raise HTTPException(status_code=404, detail="competition event not found")
    return item


@router.post("/events", status_code=201)
def create_event(req: EventCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    text_required(event_name=req.event_name, date=req.date, created_by=req.created_by)
    if not req.context:
        raise HTTPException(status_code=400, detail="context is required")
    item = {
        "event_id": str(uuid4()), "event_name": req.event_name.strip(),
        "date": req.date, "context": req.context, "created_by": req.created_by.strip(),
        "evidence_refs": req.evidence_refs, "created_at": now(),
        "coach_final_authority": True, "execution_authorized": False,
    }
    EVENTS[item["event_id"]] = item
    audit(req.created_by, "COMPETITION_EVENT_CREATED", item)
    return item


@router.get("/events/{event_id}")
def get_event(event_id: str) -> Dict[str, Any]:
    return _event(event_id)


@router.post("/readiness", status_code=201)
def capture_readiness(req: ReadinessCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    text_required(athlete_id=req.athlete_id, event_id=req.event_id, assessed_by=req.assessed_by)
    _event(req.event_id)
    if not req.indicators:
        raise HTTPException(status_code=400, detail="indicators are required")
    item = {
        "readiness_id": str(uuid4()), "athlete_id": req.athlete_id,
        "event_id": req.event_id, "indicators": req.indicators,
        "assessed_by": req.assessed_by, "evidence_refs": req.evidence_refs,
        "captured_at": now(), "coach_final_authority": True,
        "execution_authorized": False,
    }
    READINESS[item["readiness_id"]] = item
    audit(req.assessed_by, "COMPETITION_READINESS_CAPTURED", item)
    return item


@router.get("/readiness/{athlete_id}/{event_id}")
def get_readiness(athlete_id: str, event_id: str) -> Dict[str, Any]:
    records = [x for x in READINESS.values() if x["athlete_id"] == athlete_id and x["event_id"] == event_id]
    if not records:
        raise HTTPException(status_code=404, detail="readiness record not found")
    return records[-1]


@router.post("/performance", status_code=201)
def capture_performance(req: PerformanceCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    text_required(athlete_id=req.athlete_id, event_id=req.event_id, recorded_by=req.recorded_by)
    _event(req.event_id)
    if not req.performance:
        raise HTTPException(status_code=400, detail="performance is required")
    item = {
        "performance_id": str(uuid4()), "athlete_id": req.athlete_id,
        "event_id": req.event_id, "performance": req.performance,
        "recorded_by": req.recorded_by, "evidence_refs": req.evidence_refs,
        "recorded_at": now(), "coach_final_authority": True,
        "execution_authorized": False,
    }
    PERFORMANCES[item["performance_id"]] = item
    audit(req.recorded_by, "COMPETITION_PERFORMANCE_CAPTURED", item)
    return item


@router.get("/trend/{athlete_id}")
def performance_trend(athlete_id: str, event_ids: List[str]) -> Dict[str, Any]:
    if len(event_ids) < 2:
        raise HTTPException(status_code=400, detail="at least two event_ids are required")
    records = []
    for event_id in event_ids:
        matches = [x for x in PERFORMANCES.values()
                   if x["athlete_id"] == athlete_id and x["event_id"] == event_id]
        if not matches:
            raise HTTPException(status_code=404, detail=f"performance not found for event: {event_id}")
        records.append(matches[-1])
    scores: List[float] = []
    for record in records:
        score = record["performance"].get("score")
        if not isinstance(score, (int, float)):
            raise HTTPException(status_code=400, detail="each performance requires numeric performance.score")
        scores.append(float(score))
    delta = scores[-1] - scores[0]
    direction = "IMPROVING" if delta > 0 else "REGRESSING" if delta < 0 else "STABLE"
    return {
        "athlete_id": athlete_id, "event_ids": event_ids, "scores": scores,
        "delta": delta, "trend": direction, "derived_at": now(),
        "coach_final_authority": True, "execution_authorized": False,
    }


@router.post("/next-decision", status_code=201)
def create_next_decision(req: DecisionCreate) -> Dict[str, Any]:
    authority(req.coach_final_authority)
    text_required(athlete_id=req.athlete_id, event_id=req.event_id, decided_by=req.decided_by)
    _event(req.event_id)
    if not req.decision_basis or not req.decision:
        raise HTTPException(status_code=400, detail="decision_basis and decision are required")
    item = {
        "decision_id": str(uuid4()), "athlete_id": req.athlete_id,
        "event_id": req.event_id, "decision_basis": req.decision_basis,
        "decision": req.decision, "decided_by": req.decided_by,
        "evidence_refs": req.evidence_refs, "created_at": now(),
        "coach_final_authority": True, "execution_authorized": False,
    }
    DECISIONS[item["decision_id"]] = item
    audit(req.decided_by, "COMPETITION_NEXT_DECISION_RECORDED", item)
    return item
