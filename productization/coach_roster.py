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


def assign_existing_athlete(*, tenant_id: str, coach_actor_id: str,
                             athlete_id: str) -> dict[str, Any] | None:
    now = _now()
    if persistence.is_postgres_enabled():
        _ensure_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT athlete_id FROM kaizo_athletes WHERE athlete_id=%s", (athlete_id,))
                if cur.fetchone() is None:
                    return None
                cur.execute("""
                    INSERT INTO kaizo_coach_athlete_ownership
                        (athlete_id, tenant_id, coach_actor_id, assigned_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (athlete_id) DO NOTHING
                    RETURNING athlete_id
                """, (athlete_id, tenant_id, coach_actor_id, now))
                if cur.fetchone() is None:
                    return {"conflict": True}
                cur.execute("""
                    INSERT INTO kaizo_audit_logs
                        (timestamp, who, action, old_value, new_value, why, tenant_id)
                    VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                """, (now, coach_actor_id, "COACH_ATHLETE_ASSIGNED", "null",
                      json.dumps({"athlete_id": athlete_id}),
                      "Existing unassigned athlete explicitly assigned to authenticated Coach.",
                      tenant_id))
        return {"athlete_id": athlete_id, "tenant_id": tenant_id,
                "coach_actor_id": coach_actor_id, "assigned_at": now}
    if athlete_id not in _MEMORY_ATHLETES:
        # Resolve the active Core module without importing a duplicate module
        # (which would create a separate in-memory athlete registry).
        import sys
        legacy = None
        for loaded_module in tuple(sys.modules.values()):
            records = getattr(loaded_module, "ATHLETE_RECORDS", None)
            if isinstance(records, dict) and athlete_id in records:
                legacy = records[athlete_id]
                break
        if legacy is None:
            return None
        _MEMORY_ATHLETES[athlete_id] = legacy
    if athlete_id in _MEMORY_OWNERSHIP:
        return {"conflict": True}
    ownership = {"athlete_id": athlete_id, "tenant_id": tenant_id,
                 "coach_actor_id": coach_actor_id, "assigned_at": now}
    _MEMORY_OWNERSHIP[athlete_id] = ownership
    _MEMORY_AUDIT.append({"timestamp": now, "who": coach_actor_id,
                          "action": "COACH_ATHLETE_ASSIGNED", "tenant_id": tenant_id,
                          "athlete_id": athlete_id})
    return ownership


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
