"""Durable, Coach-owned decision-cycle records.

A decision cycle is distinct from FEAT-025 decision records. Each cycle binds the
verified Coach, tenant, athlete, original decision inputs/output and any later
adaptation. PostgreSQL writes pair the domain mutation with tenant audit in one
transaction. The in-memory adapter is for tests/development only.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import persistence

_MEMORY: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _memory_athlete_is_owned(*, tenant_id: str, coach_actor_id: str,
                             athlete_id: str) -> bool:
    from . import coach_roster
    return coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    ) is not None


def create_cycle(*, tenant_id: str, coach_actor_id: str, athlete_id: str,
                 case_id: str, decision_input: dict[str, Any],
                 decision_output: dict[str, Any]) -> dict[str, Any] | None:
    cycle_id = str(uuid.uuid4())
    now = _now()
    status = str(decision_output.get("status") or "RECORDED")
    cycle = {
        "decision_cycle_id": cycle_id, "tenant_id": tenant_id,
        "coach_actor_id": coach_actor_id, "athlete_id": athlete_id,
        "case_id": case_id, "decision_input": decision_input,
        "decision_output": decision_output, "adaptation_input": None,
        "adaptation_output": None, "status": status, "version": 1,
        "created_at": now, "updated_at": now,
    }
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                # Revalidate and lock the authoritative owner row in the same
                # transaction as the cycle and audit inserts.
                cur.execute(
                    """SELECT 1 FROM kaizo_coach_athlete_ownership
                       WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                       FOR UPDATE""",
                    (tenant_id, coach_actor_id, athlete_id),
                )
                if cur.fetchone() is None:
                    return None
                cur.execute(
                    """INSERT INTO kaizo_coach_decision_cycles
                       (decision_cycle_id,tenant_id,coach_actor_id,athlete_id,case_id,
                        decision_input,decision_output,adaptation_input,adaptation_output,
                        status,version,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,NULL,NULL,%s,1,%s,%s)""",
                    (cycle_id, tenant_id, coach_actor_id, athlete_id, case_id,
                     json.dumps(decision_input), json.dumps(decision_output), status, now, now),
                )
                cur.execute(
                    """INSERT INTO kaizo_audit_logs
                       (timestamp,who,action,old_value,new_value,why,tenant_id)
                       VALUES (%s,%s,%s,NULL,%s::jsonb,%s,%s)""",
                    (now, coach_actor_id, "COACH_DECISION_CYCLE_CREATED",
                     json.dumps({"decision_cycle_id": cycle_id, "athlete_id": athlete_id,
                                 "case_id": case_id, "status": status}),
                     "Persisted Coach decision cycle and audit event atomically.", tenant_id),
                )
    else:
        if not _memory_athlete_is_owned(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
        ):
            return None
        _MEMORY[cycle_id] = cycle
    return cycle


def get_owned_cycle(*, decision_cycle_id: str, tenant_id: str,
                    coach_actor_id: str, athlete_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT c.decision_cycle_id,c.tenant_id,c.coach_actor_id,c.athlete_id,c.case_id,
                              c.decision_input,c.decision_output,c.adaptation_input,c.adaptation_output,
                              c.status,c.version,c.created_at,c.updated_at
                       FROM kaizo_coach_decision_cycles c
                       JOIN kaizo_coach_athlete_ownership o
                         ON o.athlete_id=c.athlete_id
                        AND o.tenant_id=c.tenant_id
                        AND o.coach_actor_id=c.coach_actor_id
                       WHERE c.decision_cycle_id=%s AND c.tenant_id=%s
                         AND c.coach_actor_id=%s AND c.athlete_id=%s
                       FOR SHARE OF o""",
                    (decision_cycle_id, tenant_id, coach_actor_id, athlete_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        keys = ("decision_cycle_id","tenant_id","coach_actor_id","athlete_id","case_id",
                "decision_input","decision_output","adaptation_input","adaptation_output",
                "status","version","created_at","updated_at")
        return dict(zip(keys, row))
    cycle = _MEMORY.get(decision_cycle_id)
    if (not cycle
        or not _memory_athlete_is_owned(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
        )
        or any(cycle.get(k) != v for k, v in {
            "tenant_id": tenant_id, "coach_actor_id": coach_actor_id, "athlete_id": athlete_id
        }.items())):
        return None
    return dict(cycle)


def record_adaptation(*, decision_cycle_id: str, tenant_id: str,
                      coach_actor_id: str, athlete_id: str, case_id: str,
                      adaptation_input: dict[str, Any],
                      adaptation_output: dict[str, Any]) -> dict[str, Any] | None:
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                # Revalidate and lock current athlete ownership in the same
                # transaction as the cycle update and audit write.
                cur.execute(
                    """SELECT 1 FROM kaizo_coach_athlete_ownership
                       WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                       FOR UPDATE""",
                    (tenant_id, coach_actor_id, athlete_id),
                )
                if cur.fetchone() is None:
                    return None
                cur.execute(
                    """UPDATE kaizo_coach_decision_cycles
                       SET adaptation_input=%s::jsonb, adaptation_output=%s::jsonb,
                           status=%s, version=version+1, updated_at=%s
                       WHERE decision_cycle_id=%s AND tenant_id=%s
                         AND coach_actor_id=%s AND athlete_id=%s AND case_id=%s
                       RETURNING decision_cycle_id,tenant_id,coach_actor_id,athlete_id,case_id,
                                 decision_input,decision_output,adaptation_input,adaptation_output,
                                 status,version,created_at,updated_at""",
                    (json.dumps(adaptation_input), json.dumps(adaptation_output),
                     str(adaptation_output.get("status") or "ADAPTED"), now,
                     decision_cycle_id, tenant_id, coach_actor_id, athlete_id, case_id),
                )
                row = cur.fetchone()
                if row is None:
                    return None
                cur.execute(
                    """INSERT INTO kaizo_audit_logs
                       (timestamp,who,action,old_value,new_value,why,tenant_id)
                       VALUES (%s,%s,%s,NULL,%s::jsonb,%s,%s)""",
                    (now, coach_actor_id, "COACH_DECISION_CYCLE_ADAPTED",
                     json.dumps({"decision_cycle_id": decision_cycle_id,
                                 "athlete_id": athlete_id,
                                 "status": adaptation_output.get("status")}),
                     "Persisted Coach adaptation and audit event atomically.", tenant_id),
                )
        keys = ("decision_cycle_id","tenant_id","coach_actor_id","athlete_id","case_id",
                "decision_input","decision_output","adaptation_input","adaptation_output",
                "status","version","created_at","updated_at")
        return dict(zip(keys, row))
    cycle = _MEMORY.get(decision_cycle_id)
    if (not cycle
        or not _memory_athlete_is_owned(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
        )
        or cycle.get("case_id") != case_id
        or any(cycle.get(k) != v for k, v in {
            "tenant_id": tenant_id, "coach_actor_id": coach_actor_id, "athlete_id": athlete_id
        }.items())):
        return None
    cycle.update({"adaptation_input": adaptation_input,
                  "adaptation_output": adaptation_output,
                  "status": str(adaptation_output.get("status") or "ADAPTED"),
                  "version": int(cycle["version"]) + 1, "updated_at": now})
    return dict(cycle)


def reset_memory_state() -> None:
    """Test helper; never touches PostgreSQL."""
    _MEMORY.clear()
