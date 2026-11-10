"""Protected FEAT-016 Coach problem statements.

All athlete access is scoped to the verified Coach + tenant ownership row.
Writes lock ownership, validate assessment lineage, and append tenant audit
inside the same PostgreSQL transaction. The memory adapter is test-only.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import persistence
from . import coach_roster, coach_assessment_workflow


_MEMORY: dict[str, dict[str, Any]] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(row: Any) -> dict[str, Any]:
    return {
        "problem_id": row[0], "athlete_id": row[1], "assessment_id": row[2],
        "statement": row[3], "problem_type": row[4], "impact": row[5],
        "context": row[6], "structured_fields": row[7], "status": row[8],
        "created_by": row[9], "created_at": row[10], "updated_at": row[11],
    }


def _lock_owned(cur: Any, tenant_id: str, coach_actor_id: str, athlete_id: str) -> bool:
    cur.execute(
        """SELECT 1 FROM kaizo_coach_athlete_ownership
           WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
           FOR UPDATE""",
        (tenant_id, coach_actor_id, athlete_id),
    )
    return cur.fetchone() is not None


def create_problem_statement(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
    assessment_id: str, statement: str, problem_type: str,
    impact: str | None = None, context: dict[str, Any] | None = None,
    structured_fields: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    statement = str(statement or "").strip()
    problem_type = str(problem_type or "").strip()
    if not statement or not problem_type or not str(assessment_id or "").strip():
        raise ValueError("assessment_id, statement and problem_type are required")
    if context is not None and not isinstance(context, dict):
        raise ValueError("context must be an object")
    if structured_fields is not None and not isinstance(structured_fields, dict):
        raise ValueError("structured_fields must be an object")
    now = _now()
    record = {
        "problem_id": str(uuid.uuid4()), "athlete_id": athlete_id,
        "assessment_id": assessment_id, "statement": statement,
        "problem_type": problem_type, "impact": str(impact).strip() if impact else None,
        "context": context or {}, "structured_fields": structured_fields or {},
        "status": "OPEN", "created_by": coach_actor_id,
        "created_at": now, "updated_at": now,
    }
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                if not _lock_owned(cur, tenant_id, coach_actor_id, athlete_id):
                    return None
                cur.execute(
                    "SELECT 1 FROM kaizo_assessments WHERE assessment_id=%s AND athlete_id=%s",
                    (assessment_id, athlete_id),
                )
                if cur.fetchone() is None:
                    raise LookupError("assessment not found in owned athlete scope")
                cur.execute(
                    """INSERT INTO kaizo_problem_statements
                       (problem_id,athlete_id,assessment_id,statement,problem_type,impact,
                        context,structured_fields,status,created_by,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s)""",
                    (record["problem_id"], athlete_id, assessment_id, statement,
                     problem_type, record["impact"], json.dumps(record["context"]),
                     json.dumps(record["structured_fields"]), "OPEN", coach_actor_id, now, now),
                )
            persistence.append_tenant_audit(
                tenant_id=tenant_id, timestamp=now, who=coach_actor_id,
                action="COACH_PROBLEM_STATEMENT_CREATED", old_value=None,
                new_value=record, why="Structured problem statement created under verified Coach ownership.",
            )
    else:
        if coach_roster.get_owned_athlete(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
        ) is None:
            return None
        assessment = coach_assessment_workflow.get_assessment(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, assessment_id=assessment_id,
        )
        if assessment is None:
            raise LookupError("assessment not found in owned athlete scope")
        _MEMORY[record["problem_id"]] = record
    return record


def get_problem_statement(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, problem_id: str,
) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT p.problem_id,p.athlete_id,p.assessment_id,p.statement,
                              p.problem_type,p.impact,p.context,p.structured_fields,
                              p.status,p.created_by,p.created_at,p.updated_at
                       FROM kaizo_problem_statements p
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=p.athlete_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                         AND p.athlete_id=%s AND p.problem_id=%s""",
                    (tenant_id, coach_actor_id, athlete_id, problem_id),
                )
                row = cur.fetchone()
        return _row(row) if row else None
    if coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    ) is None:
        return None
    record = _MEMORY.get(problem_id)
    return record if record and record["athlete_id"] == athlete_id else None


def list_problem_statements(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT p.problem_id,p.athlete_id,p.assessment_id,p.statement,
                              p.problem_type,p.impact,p.context,p.structured_fields,
                              p.status,p.created_by,p.created_at,p.updated_at
                       FROM kaizo_problem_statements p
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=p.athlete_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s AND p.athlete_id=%s
                       ORDER BY p.created_at,p.problem_id""",
                    (tenant_id, coach_actor_id, athlete_id),
                )
                rows = cur.fetchall()
        return [_row(row) for row in rows] if rows or _owned_exists(tenant_id, coach_actor_id, athlete_id) else None
    if coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    ) is None:
        return None
    return sorted(
        [x for x in _MEMORY.values() if x["athlete_id"] == athlete_id],
        key=lambda x: (x["created_at"], x["problem_id"]),
    )


def _owned_exists(tenant_id: str, coach_actor_id: str, athlete_id: str) -> bool:
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s""",
                (tenant_id, coach_actor_id, athlete_id),
            )
            return cur.fetchone() is not None
