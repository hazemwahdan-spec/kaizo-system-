"""KAIZO Academy Operations runtime — FEAT-061..065.

Quality-first operational boundary for academy identity, coach roles, groups,
multi-coach athlete assignment, and a derived operational dashboard.
Coach Final Authority is retained for every write; this runtime never authorizes
autonomous execution.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import persistence

router = APIRouter(prefix="/api/v1/academy", tags=["Academy Operations"])

ACADEMIES: Dict[str, Dict[str, Any]] = {}
MEMBERSHIPS: Dict[str, Dict[str, Any]] = {}
GROUPS: Dict[str, Dict[str, Any]] = {}
ASSIGNMENTS: Dict[str, Dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pg_enabled() -> bool:
    return persistence.is_postgres_enabled()


def _ensure_schema() -> None:
    if not _pg_enabled():
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_academies (
                    academy_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS kaizo_academy_memberships (
                    membership_id TEXT PRIMARY KEY,
                    academy_id TEXT NOT NULL,
                    coach_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (academy_id, coach_id)
                );
                CREATE TABLE IF NOT EXISTS kaizo_academy_groups (
                    group_id TEXT PRIMARY KEY,
                    academy_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (academy_id, name)
                );
                CREATE TABLE IF NOT EXISTS kaizo_academy_assignments (
                    assignment_id TEXT PRIMARY KEY,
                    academy_id TEXT NOT NULL,
                    athlete_id TEXT NOT NULL,
                    coach_ids JSONB NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_kaizo_academy_memberships_academy
                    ON kaizo_academy_memberships(academy_id);
                CREATE INDEX IF NOT EXISTS idx_kaizo_academy_groups_academy
                    ON kaizo_academy_groups(academy_id);
                CREATE INDEX IF NOT EXISTS idx_kaizo_academy_assignments_academy
                    ON kaizo_academy_assignments(academy_id);
            """)
        conn.commit()


def _audit(actor_id: str, action: str, record: Dict[str, Any]) -> None:
    if _pg_enabled():
        try:
            persistence.append_audit({
                "actor_id": actor_id,
                "action": action,
                "occurred_at": _now(),
                "payload": record,
                "evidence_refs": [],
                "coach_final_authority": True,
                "execution_authorized": False,
            })
        except Exception:
            pass


class AcademyCreate(BaseModel):
    name: str
    owner_id: str
    status: str = "ACTIVE"
    coach_final_authority: bool = True


class MembershipCreate(BaseModel):
    academy_id: str
    coach_id: str
    role: str
    coach_final_authority: bool = True


class GroupCreate(BaseModel):
    academy_id: str
    name: str
    coach_final_authority: bool = True


class AssignmentCreate(BaseModel):
    academy_id: str
    athlete_id: str
    coach_ids: List[str] = Field(min_length=1)
    coach_final_authority: bool = True


def _require_authority(value: bool) -> None:
    if not value:
        raise HTTPException(
            status_code=409,
            detail="COACH_FINAL_AUTHORITY_REQUIRED",
        )


def _require_text(*pairs: tuple[str, str]) -> None:
    for field, value in pairs:
        if not value.strip():
            raise HTTPException(status_code=400, detail=f"{field} is required")


def _academy(academy_id: str) -> Dict[str, Any]:
    item = persistence.get_academy(academy_id) if _pg_enabled() and hasattr(persistence, "get_academy") else None
    if item is None:
        item = ACADEMIES.get(academy_id)
    if item is None:
        raise HTTPException(status_code=404, detail="academy not found")
    return item


def _membership_exists(academy_id: str, coach_id: str) -> bool:
    if _pg_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM kaizo_academy_memberships WHERE academy_id=%s AND coach_id=%s AND status='ACTIVE'",
                    (academy_id, coach_id),
                )
                if cur.fetchone():
                    return True
    return any(
        x["academy_id"] == academy_id and x["coach_id"] == coach_id and x["status"] == "ACTIVE"
        for x in MEMBERSHIPS.values()
    )


@router.post("/academies", status_code=201)
def create_academy(req: AcademyCreate) -> Dict[str, Any]:
    _require_authority(req.coach_final_authority)
    _require_text(("name", req.name), ("owner_id", req.owner_id))
    if req.status not in {"ACTIVE", "INACTIVE", "ARCHIVED"}:
        raise HTTPException(status_code=400, detail="invalid academy status")
    if any(x["name"].strip().casefold() == req.name.strip().casefold() for x in ACADEMIES.values()):
        raise HTTPException(status_code=409, detail="academy name already exists")
    now = _now()
    item = {
        "academy_id": str(uuid4()),
        "name": req.name.strip(),
        "status": req.status,
        "owner_id": req.owner_id.strip(),
        "created_at": now,
        "updated_at": now,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    ACADEMIES[item["academy_id"]] = item
    if _pg_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO kaizo_academies
                    (academy_id,name,status,owner_id,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (item["academy_id"], item["name"], item["status"], item["owner_id"], now, now),
                )
            conn.commit()
    _audit(req.owner_id, "ACADEMY_CREATED", item)
    return item


@router.get("/academies/{academy_id}")
def get_academy(academy_id: str) -> Dict[str, Any]:
    return _academy(academy_id)


@router.post("/memberships", status_code=201)
def add_membership(req: MembershipCreate) -> Dict[str, Any]:
    _require_authority(req.coach_final_authority)
    _require_text(("academy_id", req.academy_id), ("coach_id", req.coach_id), ("role", req.role))
    _academy(req.academy_id)
    if req.role not in {"OWNER", "ADMIN", "HEAD_COACH", "COACH", "ASSISTANT"}:
        raise HTTPException(status_code=400, detail="invalid coach role")
    if _membership_exists(req.academy_id, req.coach_id):
        raise HTTPException(status_code=409, detail="coach is already an active academy member")
    now = _now()
    item = {
        "membership_id": str(uuid4()),
        "academy_id": req.academy_id,
        "coach_id": req.coach_id,
        "role": req.role,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    MEMBERSHIPS[item["membership_id"]] = item
    if _pg_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO kaizo_academy_memberships
                    (membership_id,academy_id,coach_id,role,status,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (item["membership_id"], item["academy_id"], item["coach_id"], item["role"],
                     item["status"], now, now),
                )
            conn.commit()
    _audit(req.coach_id, "ACADEMY_COACH_MEMBERSHIP_CREATED", item)
    return item


@router.post("/groups", status_code=201)
def create_group(req: GroupCreate) -> Dict[str, Any]:
    _require_authority(req.coach_final_authority)
    _require_text(("academy_id", req.academy_id), ("name", req.name))
    _academy(req.academy_id)
    duplicate = any(
        x["academy_id"] == req.academy_id and x["name"].casefold() == req.name.strip().casefold()
        for x in GROUPS.values()
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="group name already exists in academy")
    now = _now()
    item = {
        "group_id": str(uuid4()),
        "academy_id": req.academy_id,
        "name": req.name.strip(),
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    GROUPS[item["group_id"]] = item
    if _pg_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO kaizo_academy_groups
                    (group_id,academy_id,name,status,created_at,updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s)""",
                    (item["group_id"], item["academy_id"], item["name"], item["status"], now, now),
                )
            conn.commit()
    _audit("system", "ACADEMY_GROUP_CREATED", item)
    return item


@router.post("/assignments", status_code=201)
def assign_athlete(req: AssignmentCreate) -> Dict[str, Any]:
    _require_authority(req.coach_final_authority)
    _require_text(("academy_id", req.academy_id), ("athlete_id", req.athlete_id))
    _academy(req.academy_id)
    coach_ids = list(dict.fromkeys(c.strip() for c in req.coach_ids if c.strip()))
    if not coach_ids:
        raise HTTPException(status_code=400, detail="coach_ids must contain at least one coach")
    missing = [c for c in coach_ids if not _membership_exists(req.academy_id, c)]
    if missing:
        raise HTTPException(status_code=409, detail=f"coach membership required for: {','.join(missing)}")
    now = _now()
    existing = next(
        (x for x in ASSIGNMENTS.values()
         if x["academy_id"] == req.academy_id and x["athlete_id"] == req.athlete_id and x["status"] == "ACTIVE"),
        None,
    )
    if existing:
        existing.update({"coach_ids": coach_ids, "updated_at": now})
        _audit("system", "ATHLETE_COACH_ASSIGNMENT_UPDATED", existing)
        return existing
    item = {
        "assignment_id": str(uuid4()),
        "academy_id": req.academy_id,
        "athlete_id": req.athlete_id,
        "coach_ids": coach_ids,
        "status": "ACTIVE",
        "created_at": now,
        "updated_at": now,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
    ASSIGNMENTS[item["assignment_id"]] = item
    if _pg_enabled():
        _ensure_schema()
        import json
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO kaizo_academy_assignments
                    (assignment_id,academy_id,athlete_id,coach_ids,status,created_at,updated_at)
                    VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                    (item["assignment_id"], item["academy_id"], item["athlete_id"],
                     json.dumps(coach_ids), item["status"], now, now),
                )
            conn.commit()
    _audit("system", "ATHLETE_MULTI_COACH_ASSIGNED", item)
    return item


@router.get("/academies/{academy_id}/dashboard")
def academy_dashboard(academy_id: str) -> Dict[str, Any]:
    academy = _academy(academy_id)
    members = [x for x in MEMBERSHIPS.values() if x["academy_id"] == academy_id and x["status"] == "ACTIVE"]
    groups = [x for x in GROUPS.values() if x["academy_id"] == academy_id and x["status"] == "ACTIVE"]
    assignments = [x for x in ASSIGNMENTS.values() if x["academy_id"] == academy_id and x["status"] == "ACTIVE"]
    coach_loads: Dict[str, int] = {m["coach_id"]: 0 for m in members}
    for assignment in assignments:
        for coach_id in assignment["coach_ids"]:
            coach_loads[coach_id] = coach_loads.get(coach_id, 0) + 1
    return {
        "academy_id": academy_id,
        "academy_name": academy["name"],
        "status": academy["status"],
        "metrics": {
            "active_coaches": len(members),
            "active_groups": len(groups),
            "assigned_athletes": len(assignments),
            "multi_coach_athletes": sum(1 for x in assignments if len(x["coach_ids"]) > 1),
            "coach_assignment_loads": coach_loads,
        },
        "derived_at": _now(),
        "coach_final_authority": True,
        "execution_authorized": False,
    }
