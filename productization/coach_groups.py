"""Tenant- and Coach-scoped training groups with durable membership audit."""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Any
import persistence

_GROUPS: dict[str, dict[str, Any]] = {}
_MEMBERS: set[tuple[str, str]] = set()
_AUDIT: list[dict[str, Any]] = []

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _schema() -> None:
    if not persistence.is_postgres_enabled():
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_coach_training_groups (
                    group_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    coach_actor_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (tenant_id, coach_actor_id, name)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_coach_training_groups_scope
                ON kaizo_coach_training_groups (tenant_id, coach_actor_id, created_at)
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_coach_training_group_members (
                    group_id TEXT NOT NULL REFERENCES kaizo_coach_training_groups(group_id) ON DELETE CASCADE,
                    athlete_id TEXT NOT NULL REFERENCES kaizo_athletes(athlete_id) ON DELETE CASCADE,
                    tenant_id TEXT NOT NULL,
                    coach_actor_id TEXT NOT NULL,
                    assigned_at TEXT NOT NULL,
                    PRIMARY KEY (group_id, athlete_id)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_coach_group_members_scope
                ON kaizo_coach_training_group_members (tenant_id, coach_actor_id, group_id)
            """)
        conn.commit()

def create_group(*, tenant_id: str, coach_actor_id: str, name: str) -> dict[str, Any]:
    clean=name.strip()
    if not clean: raise ValueError("group name is required")
    item={"group_id":str(uuid.uuid4()),"tenant_id":tenant_id,"coach_actor_id":coach_actor_id,"name":clean,"created_at":_now(),"athletes":[]}
    if persistence.is_postgres_enabled():
        _schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO kaizo_coach_training_groups
                    (group_id,tenant_id,coach_actor_id,name,created_at) VALUES (%s,%s,%s,%s,%s)""",
                    (item["group_id"],tenant_id,coach_actor_id,clean,item["created_at"]))
                cur.execute("""INSERT INTO kaizo_audit_logs
                    (timestamp,who,action,old_value,new_value,why,tenant_id)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)""",
                    (item["created_at"],coach_actor_id,"COACH_TRAINING_GROUP_CREATED","null",
                     json.dumps({"group_id":item["group_id"],"name":clean}),
                     "Training group created by its verified Coach.",tenant_id))
    else:
        _GROUPS[item["group_id"]]=item
        _AUDIT.append({"action":"COACH_TRAINING_GROUP_CREATED","tenant_id":tenant_id,"who":coach_actor_id,"group_id":item["group_id"]})
    return item

def list_groups(*, tenant_id: str, coach_actor_id: str) -> list[dict[str, Any]]:
    if persistence.is_postgres_enabled():
        _schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT g.group_id,g.name,g.created_at,a.athlete_id,a.display_name
                    FROM kaizo_coach_training_groups g
                    LEFT JOIN kaizo_coach_training_group_members m ON m.group_id=g.group_id
                      AND m.tenant_id=g.tenant_id AND m.coach_actor_id=g.coach_actor_id
                    LEFT JOIN kaizo_athletes a ON a.athlete_id=m.athlete_id
                    WHERE g.tenant_id=%s AND g.coach_actor_id=%s
                    ORDER BY g.created_at,g.name,a.display_name""",(tenant_id,coach_actor_id))
                rows=cur.fetchall()
        groups={}
        for gid,name,created,aid,display in rows:
            groups.setdefault(gid,{"group_id":gid,"name":name,"created_at":created,"athletes":[]})
            if aid: groups[gid]["athletes"].append({"athlete_id":aid,"display_name":display})
        return list(groups.values())
    out=[]
    for g in _GROUPS.values():
        if g["tenant_id"]==tenant_id and g["coach_actor_id"]==coach_actor_id:
            item={**g,"athletes":[]}
            for gid,aid in _MEMBERS:
                if gid==g["group_id"]:
                    item["athletes"].append({"athlete_id":aid})
            out.append(item)
    return sorted(out,key=lambda x:(x["created_at"],x["name"]))

def assign_athlete(*,tenant_id:str,coach_actor_id:str,group_id:str,athlete_id:str)->bool:
    now=_now()
    if persistence.is_postgres_enabled():
        _schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT 1 FROM kaizo_coach_training_groups
                    WHERE group_id=%s AND tenant_id=%s AND coach_actor_id=%s FOR UPDATE""",
                    (group_id,tenant_id,coach_actor_id))
                if not cur.fetchone(): return False
                cur.execute("""SELECT 1 FROM kaizo_coach_athlete_ownership
                    WHERE athlete_id=%s AND tenant_id=%s AND coach_actor_id=%s""",
                    (athlete_id,tenant_id,coach_actor_id))
                if not cur.fetchone(): return False
                cur.execute("""INSERT INTO kaizo_coach_training_group_members
                    (group_id,athlete_id,tenant_id,coach_actor_id,assigned_at)
                    VALUES (%s,%s,%s,%s,%s) ON CONFLICT (group_id,athlete_id) DO NOTHING""",
                    (group_id,athlete_id,tenant_id,coach_actor_id,now))
                changed=cur.rowcount>0
                if changed:
                    cur.execute("""INSERT INTO kaizo_audit_logs
                        (timestamp,who,action,old_value,new_value,why,tenant_id)
                        VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)""",
                        (now,coach_actor_id,"COACH_TRAINING_GROUP_ATHLETE_ASSIGNED","null",
                         json.dumps({"group_id":group_id,"athlete_id":athlete_id}),
                         "Owned athlete assigned to Coach-owned training group.",tenant_id))
                return True
    group=_GROUPS.get(group_id)
    owner=__import__("productization.coach_roster",fromlist=["_MEMORY_OWNERSHIP"])._MEMORY_OWNERSHIP.get(athlete_id)
    if not group or group["tenant_id"]!=tenant_id or group["coach_actor_id"]!=coach_actor_id or not owner or owner["tenant_id"]!=tenant_id or owner["coach_actor_id"]!=coach_actor_id:
        return False
    if (group_id,athlete_id) not in _MEMBERS:
        _MEMBERS.add((group_id,athlete_id));_AUDIT.append({"action":"COACH_TRAINING_GROUP_ATHLETE_ASSIGNED","tenant_id":tenant_id,"who":coach_actor_id,"group_id":group_id,"athlete_id":athlete_id})
    return True

def unassign_athlete(*,tenant_id:str,coach_actor_id:str,group_id:str,athlete_id:str)->bool:
    now=_now()
    if persistence.is_postgres_enabled():
        _schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT 1 FROM kaizo_coach_training_groups
                    WHERE group_id=%s AND tenant_id=%s AND coach_actor_id=%s""",(group_id,tenant_id,coach_actor_id))
                if not cur.fetchone(): return False
                cur.execute("""DELETE FROM kaizo_coach_training_group_members
                    WHERE group_id=%s AND athlete_id=%s AND tenant_id=%s AND coach_actor_id=%s""",
                    (group_id,athlete_id,tenant_id,coach_actor_id))
                if cur.rowcount:
                    cur.execute("""INSERT INTO kaizo_audit_logs
                        (timestamp,who,action,old_value,new_value,why,tenant_id)
                        VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)""",
                        (now,coach_actor_id,"COACH_TRAINING_GROUP_ATHLETE_UNASSIGNED",
                         json.dumps({"group_id":group_id,"athlete_id":athlete_id}),"null",
                         "Athlete removed from Coach-owned training group.",tenant_id))
                return True
    group=_GROUPS.get(group_id)
    if not group or group["tenant_id"]!=tenant_id or group["coach_actor_id"]!=coach_actor_id:return False
    _MEMBERS.discard((group_id,athlete_id))
    _AUDIT.append({"action":"COACH_TRAINING_GROUP_ATHLETE_UNASSIGNED","tenant_id":tenant_id,"who":coach_actor_id,"group_id":group_id,"athlete_id":athlete_id})
    return True

def reset_memory_state()->None:
    _GROUPS.clear();_MEMBERS.clear();_AUDIT.clear()
