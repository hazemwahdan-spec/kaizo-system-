"""Secure, single-Coach ownership boundary for the commercial Coach roster.

Legacy athlete rows remain unassigned until explicitly claimed by an authenticated
Coach. All ownership reads are scoped by the verified principal's tenant and actor.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import persistence

# Test/development adapter only. Production requires PostgreSQL durability.
_MEMORY_OWNERSHIP: dict[str, dict[str, Any]] = {}
_MEMORY_ATHLETES: dict[str, dict[str, Any]] = {}
_MEMORY_AUDIT: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_schema() -> None:
    if not persistence.is_postgres_enabled():
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kaizo_coach_athlete_ownership (
                    athlete_id TEXT PRIMARY KEY REFERENCES kaizo_athletes(athlete_id) ON DELETE CASCADE,
                    tenant_id TEXT NOT NULL,
                    coach_actor_id TEXT NOT NULL,
                    assigned_at TEXT NOT NULL,
                    CONSTRAINT uq_coach_athlete_scope UNIQUE (tenant_id, coach_actor_id, athlete_id)
                )
            """)
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_coach_roster_scope
                ON kaizo_coach_athlete_ownership (tenant_id, coach_actor_id, assigned_at)
            """)
        conn.commit()


def create_owned_athlete(*, tenant_id: str, coach_actor_id: str, display_name: str,
                         metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    name = display_name.strip()
    if not name:
        raise ValueError("display_name is required")
    now = _now()
    athlete = {
        "athlete_id": str(uuid.uuid4()), "display_name": name, "status": "ACTIVE",
        "metadata": metadata or {}, "created_at": now, "updated_at": now,
    }
    ownership = {
        "athlete_id": athlete["athlete_id"], "tenant_id": tenant_id,
        "coach_actor_id": coach_actor_id, "assigned_at": now,
    }
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO kaizo_athletes
                        (athlete_id, display_name, status, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                """, (athlete["athlete_id"], name, "ACTIVE",
                      json.dumps(athlete["metadata"]), now, now))
                cur.execute("""
                    INSERT INTO kaizo_coach_athlete_ownership
                        (athlete_id, tenant_id, coach_actor_id, assigned_at)
                    VALUES (%s, %s, %s, %s)
                """, (athlete["athlete_id"], tenant_id, coach_actor_id, now))
                cur.execute("""
                    INSERT INTO kaizo_audit_logs
                        (timestamp, who, action, old_value, new_value, why, tenant_id)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                """, (now, coach_actor_id, "COACH_ATHLETE_CREATED", "null",
                      json.dumps({"athlete_id": athlete["athlete_id"]}),
                      "Athlete created and assigned atomically to the authenticated Coach.",
                      tenant_id))
    else:
        _MEMORY_ATHLETES[athlete["athlete_id"]] = athlete
        # Keep the Core's existing in-memory athlete registry consistent so
        # subsequent assessment/decision routes can resolve this new athlete.
        import sys
        for loaded_module in tuple(sys.modules.values()):
            records = getattr(loaded_module, "ATHLETE_RECORDS", None)
            if isinstance(records, dict):
                records[athlete["athlete_id"]] = athlete
                break
        _MEMORY_OWNERSHIP[athlete["athlete_id"]] = ownership
        _MEMORY_AUDIT.append({"timestamp": now, "who": coach_actor_id,
                              "action": "COACH_ATHLETE_CREATED", "tenant_id": tenant_id,
                              "athlete_id": athlete["athlete_id"]})
    return athlete


def get_owned_athlete(*, tenant_id: str, coach_actor_id: str,
                      athlete_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.athlete_id, a.display_name, a.status, a.metadata,
                           a.created_at, a.updated_at
                    FROM kaizo_athletes a
                    JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
                    WHERE o.tenant_id=%s AND o.coach_actor_id=%s AND o.athlete_id=%s
                """, (tenant_id, coach_actor_id, athlete_id))
                row = cur.fetchone()
        if row is None:
            return None
        return {"athlete_id": row[0], "display_name": row[1], "status": row[2],
                "metadata": row[3], "created_at": row[4], "updated_at": row[5]}
    owner = _MEMORY_OWNERSHIP.get(athlete_id)
    if not owner or owner["tenant_id"] != tenant_id or owner["coach_actor_id"] != coach_actor_id:
        return None
    return _MEMORY_ATHLETES.get(athlete_id)


def list_owned_athletes(*, tenant_id: str, coach_actor_id: str) -> list[dict[str, Any]]:
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT a.athlete_id, a.display_name, a.status, a.metadata,
                           a.created_at, a.updated_at
                    FROM kaizo_athletes a
                    JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
                    WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                    ORDER BY a.display_name, a.athlete_id
                """, (tenant_id, coach_actor_id))
                rows = cur.fetchall()
        return [{"athlete_id": r[0], "display_name": r[1], "status": r[2],
                 "metadata": r[3], "created_at": r[4], "updated_at": r[5]} for r in rows]
    ids = [athlete_id for athlete_id, owner in _MEMORY_OWNERSHIP.items()
           if owner["tenant_id"] == tenant_id and owner["coach_actor_id"] == coach_actor_id]
    return sorted((_MEMORY_ATHLETES[i] for i in ids), key=lambda a: a["display_name"])


def reset_memory_state() -> None:
    """Test helper; does not affect PostgreSQL."""
    _MEMORY_OWNERSHIP.clear()
    _MEMORY_ATHLETES.clear()
    _MEMORY_AUDIT.clear()
    if "update_owned_athlete_status" in globals():
        update_owned_athlete_status._history = []


# FEAT-004: controlled lifecycle transitions for a Coach-owned athlete.
ATHLETE_STATUSES = {"ACTIVE", "INACTIVE", "SUSPENDED", "ARCHIVED"}
_STATUS_TRANSITIONS = {
    "ACTIVE": {"INACTIVE", "SUSPENDED", "ARCHIVED"},
    "INACTIVE": {"ACTIVE", "ARCHIVED"},
    "SUSPENDED": {"ACTIVE", "INACTIVE", "ARCHIVED"},
    "ARCHIVED": set(),
}

def update_owned_athlete_status(*, tenant_id: str, coach_actor_id: str,
                                athlete_id: str, new_status: str,
                                reason: str) -> dict[str, Any] | None:
    target = new_status.strip().upper()
    explanation = reason.strip()
    if target not in ATHLETE_STATUSES:
        raise ValueError("status must be ACTIVE, INACTIVE, SUSPENDED, or ARCHIVED")
    if not explanation:
        raise ValueError("a reason is required for every lifecycle transition")
    now = _now()
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS kaizo_coach_athlete_status_history (
                        history_id TEXT PRIMARY KEY,
                        athlete_id TEXT NOT NULL REFERENCES kaizo_athletes(athlete_id) ON DELETE CASCADE,
                        tenant_id TEXT NOT NULL,
                        coach_actor_id TEXT NOT NULL,
                        previous_status TEXT NOT NULL,
                        new_status TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        changed_at TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_coach_athlete_status_history_scope
                    ON kaizo_coach_athlete_status_history
                    (tenant_id, coach_actor_id, athlete_id, changed_at)
                """)
                cur.execute("""
                    SELECT a.status FROM kaizo_athletes a
                    JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
                    WHERE o.tenant_id=%s AND o.coach_actor_id=%s AND o.athlete_id=%s
                    FOR UPDATE OF a
                """, (tenant_id, coach_actor_id, athlete_id))
                row = cur.fetchone()
                if row is None:
                    return None
                previous = str(row[0]).upper()
                if previous == target:
                    return {"athlete_id": athlete_id, "status": previous,
                            "changed": False, "updated_at": now}
                if target not in _STATUS_TRANSITIONS.get(previous, set()):
                    raise ValueError(f"transition {previous} -> {target} is not permitted")
                import uuid
                cur.execute("UPDATE kaizo_athletes SET status=%s, updated_at=%s WHERE athlete_id=%s",
                            (target, now, athlete_id))
                cur.execute("""
                    INSERT INTO kaizo_coach_athlete_status_history
                    (history_id, athlete_id, tenant_id, coach_actor_id,
                     previous_status, new_status, reason, changed_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (str(uuid.uuid4()), athlete_id, tenant_id, coach_actor_id,
                      previous, target, explanation, now))
                cur.execute("""
                    INSERT INTO kaizo_audit_logs
                    (timestamp, who, action, old_value, new_value, why, tenant_id)
                    VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
                """, (now, coach_actor_id, "COACH_ATHLETE_STATUS_CHANGED",
                      json.dumps({"athlete_id": athlete_id, "status": previous}),
                      json.dumps({"athlete_id": athlete_id, "status": target}),
                      explanation, tenant_id))
                return {"athlete_id": athlete_id, "status": target,
                        "previous_status": previous, "changed": True, "updated_at": now}
    owner = _MEMORY_OWNERSHIP.get(athlete_id)
    athlete = _MEMORY_ATHLETES.get(athlete_id)
    if not owner or not athlete or owner["tenant_id"] != tenant_id or owner["coach_actor_id"] != coach_actor_id:
        return None
    previous = str(athlete["status"]).upper()
    if previous == target:
        return {"athlete_id": athlete_id, "status": previous, "changed": False,
                "updated_at": athlete["updated_at"]}
    if target not in _STATUS_TRANSITIONS.get(previous, set()):
        raise ValueError(f"transition {previous} -> {target} is not permitted")
    athlete["status"] = target
    athlete["updated_at"] = now
    event = {"timestamp": now, "who": coach_actor_id,
             "action": "COACH_ATHLETE_STATUS_CHANGED", "tenant_id": tenant_id,
             "athlete_id": athlete_id, "old_status": previous,
             "new_status": target, "reason": explanation}
    _MEMORY_AUDIT.append(event)
    if not hasattr(update_owned_athlete_status, "_history"):
        update_owned_athlete_status._history = []
    update_owned_athlete_status._history.append(event)
    return {"athlete_id": athlete_id, "status": target,
            "previous_status": previous, "changed": True, "updated_at": now}

def list_owned_athlete_status_history(*, tenant_id: str, coach_actor_id: str,
                                      athlete_id: str) -> list[dict[str, Any]] | None:
    athlete = get_owned_athlete(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id)
    if athlete is None:
        return None
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""CREATE TABLE IF NOT EXISTS kaizo_coach_athlete_status_history (
                    history_id TEXT PRIMARY KEY,
                    athlete_id TEXT NOT NULL REFERENCES kaizo_athletes(athlete_id) ON DELETE CASCADE,
                    tenant_id TEXT NOT NULL, coach_actor_id TEXT NOT NULL,
                    previous_status TEXT NOT NULL, new_status TEXT NOT NULL,
                    reason TEXT NOT NULL, changed_at TEXT NOT NULL)""")
                cur.execute("""CREATE INDEX IF NOT EXISTS idx_coach_athlete_status_history_scope
                    ON kaizo_coach_athlete_status_history (tenant_id, coach_actor_id, athlete_id, changed_at)""")
                cur.execute("""
                    SELECT previous_status,new_status,reason,changed_at,coach_actor_id
                    FROM kaizo_coach_athlete_status_history
                    WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                    ORDER BY changed_at,history_id
                """, (tenant_id, coach_actor_id, athlete_id))
                rows=cur.fetchall()
        return [{"previous_status":r[0],"new_status":r[1],"reason":r[2],
                 "changed_at":r[3],"changed_by":r[4]} for r in rows]
    history=getattr(update_owned_athlete_status,"_history",[])
    return [{"previous_status":e["old_status"],"new_status":e["new_status"],
             "reason":e["reason"],"changed_at":e["timestamp"],
             "changed_by":e["who"]} for e in history
             if e["athlete_id"]==athlete_id and e["tenant_id"]==tenant_id
             and e["who"]==coach_actor_id]


# FEAT-005: derive Coach-visible decision history from existing persisted records.
def list_owned_athlete_decision_cycles(*, tenant_id: str, coach_actor_id: str,
                                       athlete_id: str) -> list[dict[str, Any]] | None:
    """Return only decision records already persisted for an owned athlete.

    No relationship is created or backfilled here. The athlete association is
    taken from the original decision record and downstream workflow records.
    """
    if get_owned_athlete(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                         athlete_id=athlete_id) is None:
        return None

    cycles: dict[str, dict[str, Any]] = {}
    if persistence.is_postgres_enabled():
        import training_workflow
        training_workflow._ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT decision_id,candidate_id,diagnosis_id,problem_id,
                                      athlete_id,assessment_id,candidate_type,coach_action,
                                      coach_id,decision_summary,outcome_intent,status,recorded_at
                               FROM kaizo_decision_records
                               WHERE athlete_id=%s
                               ORDER BY recorded_at,decision_id""", (athlete_id,))
                decisions = cur.fetchall()
                cur.execute("""SELECT record_id,feature_id,athlete_id,decision_id,session_id,
                                      created_by,created_at
                               FROM kaizo_training_workflow_records
                               WHERE athlete_id=%s AND decision_id IS NOT NULL
                               ORDER BY created_at,record_id""", (athlete_id,))
                workflow = cur.fetchall()
                cur.execute("""SELECT plan_id,athlete_id,decision_id,title,objective,status,created_at
                               FROM kaizo_training_plans WHERE athlete_id=%s
                               ORDER BY created_at,plan_id""", (athlete_id,))
                plans = cur.fetchall()
        for r in decisions:
            cycles[r[0]] = {"decision_id":r[0],"candidate_id":r[1],"diagnosis_id":r[2],
                "problem_id":r[3],"athlete_id":r[4],"assessment_id":r[5],
                "candidate_type":r[6],"coach_action":r[7],"recorded_by":r[8],
                "decision_summary":r[9],"outcome_intent":r[10],"status":r[11],
                "recorded_at":r[12],"training_records":[],"training_plans":[]}
        for r in workflow:
            cycle=cycles.get(r[3])
            if cycle is not None and r[2] == athlete_id:
                cycle["training_records"].append({"record_id":r[0],"feature_id":r[1],
                    "session_id":r[4],"created_by":r[5],"created_at":r[6]})
        for r in plans:
            cycle=cycles.get(r[2])
            if cycle is not None and r[1] == athlete_id:
                cycle["training_plans"].append({"plan_id":r[0],"title":r[3],
                    "objective":r[4],"status":r[5],"created_at":r[6]})
    else:
        import importlib, sys
        core = sys.modules.get("main") or importlib.import_module("main")
        training = sys.modules.get("training_workflow")
        decisions = getattr(core, "DECISION_RECORDS", {}).values()
        workflow = getattr(training, "_MEMORY", {}).values() if training else ()
        plans = getattr(core, "TRAINING_PLANS", {}).values()
        for item in decisions:
            if item.get("athlete_id") == athlete_id:
                cycles[item["decision_id"]] = {**item,"training_records":[],"training_plans":[]}
        for item in workflow:
            cycle=cycles.get(item.get("decision_id"))
            if cycle is not None and item.get("athlete_id") == athlete_id:
                cycle["training_records"].append({"record_id":item.get("record_id"),
                    "feature_id":item.get("feature_id"),"session_id":item.get("session_id"),
                    "created_by":item.get("created_by"),"created_at":item.get("created_at")})
        for item in plans:
            cycle=cycles.get(item.get("decision_id"))
            if cycle is not None and item.get("athlete_id") == athlete_id:
                cycle["training_plans"].append({"plan_id":item.get("plan_id"),
                    "title":item.get("title"),"objective":item.get("objective"),
                    "status":item.get("status"),"created_at":item.get("created_at")})
    return list(cycles.values())


# FEAT-006: evidence-backed Coach home dashboard summary.
def get_coach_home_dashboard(*, tenant_id: str, coach_actor_id: str) -> dict[str, Any]:
    """Aggregate only data owned by the verified Coach within the tenant.

    This is a summary surface, not a priority queue (FEAT-007). It never
    synthesizes tasks, scores, attendance, or decision records.
    """
    athletes = list_owned_athletes(tenant_id=tenant_id, coach_actor_id=coach_actor_id)
    groups_module = __import__("productization.coach_groups", fromlist=["list_groups"])
    groups = groups_module.list_groups(tenant_id=tenant_id, coach_actor_id=coach_actor_id)
    statuses = {status: 0 for status in sorted(ATHLETE_STATUSES)}
    for athlete in athletes:
        status = str(athlete.get("status") or "UNKNOWN").upper()
        statuses[status] = statuses.get(status, 0) + 1

    athlete_names = {a["athlete_id"]: a.get("display_name", a["athlete_id"]) for a in athletes}
    recent: list[dict[str, Any]] = []
    decision_total = 0
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT COUNT(*) FROM kaizo_decision_records d
                    JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=d.athlete_id
                    WHERE o.tenant_id=%s AND o.coach_actor_id=%s""", (tenant_id, coach_actor_id))
                decision_total = int(cur.fetchone()[0])
                cur.execute("""SELECT d.decision_id,d.athlete_id,a.display_name,
                                      d.decision_summary,d.status,d.recorded_at,d.coach_action
                    FROM kaizo_decision_records d
                    JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=d.athlete_id
                    JOIN kaizo_athletes a ON a.athlete_id=d.athlete_id
                    WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                    ORDER BY d.recorded_at DESC,d.decision_id DESC LIMIT 5""",
                    (tenant_id, coach_actor_id))
                rows = cur.fetchall()
        recent = [{"decision_id":r[0],"athlete_id":r[1],"athlete_name":r[2],
                   "summary":r[3],"status":r[4],"recorded_at":r[5],"coach_action":r[6]}
                  for r in rows]
    else:
        import sys
        core = sys.modules.get("main")
        records = getattr(core, "DECISION_RECORDS", {}) if core else {}
        owned = set(athlete_names)
        owned_records = [d for d in records.values() if d.get("athlete_id") in owned]
        decision_total = len(owned_records)
        owned_records.sort(key=lambda d: str(d.get("recorded_at") or ""), reverse=True)
        recent = [{"decision_id":d.get("decision_id"),"athlete_id":d.get("athlete_id"),
                   "athlete_name":athlete_names.get(d.get("athlete_id")),
                   "summary":d.get("decision_summary"),"status":d.get("status"),
                   "recorded_at":d.get("recorded_at"),"coach_action":d.get("coach_action")}
                  for d in owned_records[:5]]

    return {
        "athlete_total": len(athletes),
        "athlete_status_counts": statuses,
        "training_group_total": len(groups),
        "group_membership_total": sum(len(g.get("athletes", [])) for g in groups),
        "decision_cycle_total": decision_total,
        "recent_decisions": recent,
        "priority_queue": {"available": False, "feature": "FEAT-007"},
        "source_scope": "verified_coach_tenant_owned_records",
        "coach_final_authority": True,
        "execution_authorized": False,
    }
