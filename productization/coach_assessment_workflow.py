"""Verified Coach assessment, KPI, evidence-attachment and state-snapshot workflow.

All athlete-scoped writes lock the authoritative ownership row and persist the
domain record together with a tenant-scoped audit event. The in-memory adapter
exists only for isolated tests/development; production acceptance requires
PostgreSQL.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

import persistence
from . import coach_roster


class CoachWorkflowNotFound(LookupError):
    pass


class CoachWorkflowConflict(RuntimeError):
    pass


_MEMORY_ASSESSMENTS: dict[str, dict[str, Any]] = {}
_MEMORY_KPI_DEFINITIONS: dict[tuple[str, str, str], dict[str, Any]] = {}
_MEMORY_KPI_CAPTURES: dict[str, dict[str, Any]] = {}
_MEMORY_EVIDENCE: dict[str, dict[str, Any]] = {}
_MEMORY_ATTACHMENTS: dict[tuple[str, str], dict[str, Any]] = {}
_MEMORY_SNAPSHOTS: dict[str, dict[str, Any]] = {}
_MEMORY_AUDIT: list[dict[str, Any]] = []

_ALLOWED_KPI_DIRECTIONS = {"higher_is_better", "lower_is_better", "target_range"}
_ALLOWED_SNAPSHOT_TYPES = {"baseline", "current_state"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reset_memory_state() -> None:
    _MEMORY_ASSESSMENTS.clear()
    _MEMORY_KPI_DEFINITIONS.clear()
    _MEMORY_KPI_CAPTURES.clear()
    _MEMORY_EVIDENCE.clear()
    _MEMORY_ATTACHMENTS.clear()
    _MEMORY_SNAPSHOTS.clear()
    _MEMORY_AUDIT.clear()


def _owned_in_memory(*, tenant_id: str, coach_actor_id: str, athlete_id: str) -> bool:
    return coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    ) is not None


def _lock_owned(cur: Any, *, tenant_id: str, coach_actor_id: str, athlete_id: str) -> bool:
    cur.execute(
        """SELECT 1 FROM kaizo_coach_athlete_ownership
           WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
           FOR UPDATE""",
        (tenant_id, coach_actor_id, athlete_id),
    )
    return cur.fetchone() is not None


def _audit(*, tenant_id: str, coach_actor_id: str, action: str,
           old_value: Any, new_value: Any, why: str, timestamp: str) -> None:
    if persistence.is_postgres_enabled():
        persistence.append_tenant_audit(
            tenant_id=tenant_id, timestamp=timestamp, who=coach_actor_id,
            action=action, old_value=old_value, new_value=new_value, why=why,
        )
    else:
        _MEMORY_AUDIT.append({
            "tenant_id": tenant_id, "timestamp": timestamp, "who": coach_actor_id,
            "action": action, "old_value": old_value, "new_value": new_value, "why": why,
        })


def _ensure_kpi_schema() -> None:
    """Fail closed if the application startup migration did not create the scoped KPI table."""
    if not persistence.is_postgres_enabled():
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.kaizo_coach_kpi_definitions')")
            if cur.fetchone()[0] is None:
                raise RuntimeError("Coach KPI schema is not initialized; run the approved PostgreSQL schema migration")


def _assessment(row: Any) -> dict[str, Any]:
    return {
        "assessment_id": row[0], "athlete_id": row[1], "template_id": row[2],
        "measurements": row[3], "recorded_by": row[4],
        "assessed_at": row[5], "created_at": row[6],
    }


def _kpi_definition(row: Any) -> dict[str, Any]:
    return {
        "kpi_id": row[0], "name": row[1], "metric_name": row[2], "unit": row[3],
        "target": row[4], "direction": row[5], "status": row[6],
        "created_at": row[7], "updated_at": row[8],
    }


def _kpi_capture(row: Any) -> dict[str, Any]:
    return {
        "capture_id": row[0], "athlete_id": row[1], "kpi_id": row[2],
        "value": row[3], "captured_by": row[4], "assessment_id": row[5],
        "captured_at": row[6], "created_at": row[7],
    }


def _snapshot(row: Any) -> dict[str, Any]:
    return {
        "snapshot_id": row[0], "athlete_id": row[1], "assessment_id": row[2],
        "snapshot_type": row[3], "measurements": row[4], "kpis": row[5],
        "captured_by": row[6], "captured_at": row[7], "created_at": row[8],
    }


def create_assessment(*, tenant_id: str, coach_actor_id: str, athlete_id: str,
                      template_id: str, measurements: dict[str, Any]) -> dict[str, Any] | None:
    template_id = str(template_id or "").strip()
    if not template_id or not isinstance(measurements, dict) or not measurements:
        raise ValueError("template_id and non-empty measurements are required")
    now = _now()
    record = {
        "assessment_id": str(uuid.uuid4()), "athlete_id": athlete_id,
        "template_id": template_id, "measurements": measurements,
        "recorded_by": coach_actor_id, "assessed_at": now, "created_at": now,
    }
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                if not _lock_owned(cur, tenant_id=tenant_id,
                                   coach_actor_id=coach_actor_id, athlete_id=athlete_id):
                    return None
                cur.execute(
                    """INSERT INTO kaizo_assessments
                       (assessment_id,athlete_id,template_id,measurements,recorded_by,assessed_at,created_at)
                       VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                    (record["assessment_id"], athlete_id, template_id,
                     json.dumps(measurements), coach_actor_id, now, now),
                )
                _audit(
                    tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    action="COACH_ASSESSMENT_RECORDED", old_value=None, new_value=record,
                    why="Assessment measurements recorded under verified Coach ownership.",
                    timestamp=now,
                )
    else:
        if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id):
            return None
        _MEMORY_ASSESSMENTS[record["assessment_id"]] = record
        _audit(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            action="COACH_ASSESSMENT_RECORDED", old_value=None, new_value=record,
            why="Assessment measurements recorded under verified Coach ownership.",
            timestamp=now,
        )
    return record


def list_assessments(*, tenant_id: str, coach_actor_id: str,
                     athlete_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.assessment_id,a.athlete_id,a.template_id,a.measurements,
                              a.recorded_by,a.assessed_at,a.created_at
                       FROM kaizo_assessments a
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s AND a.athlete_id=%s
                       ORDER BY a.assessed_at,a.assessment_id""",
                    (tenant_id, coach_actor_id, athlete_id),
                )
                rows = cur.fetchall()
        return [_assessment(row) for row in rows] if _owned_exists(tenant_id, coach_actor_id, athlete_id) else None
    if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id):
        return None
    return sorted(
        [x for x in _MEMORY_ASSESSMENTS.values() if x["athlete_id"] == athlete_id],
        key=lambda x: (x["assessed_at"], x["assessment_id"]),
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


def get_assessment(*, tenant_id: str, coach_actor_id: str, athlete_id: str,
                   assessment_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT a.assessment_id,a.athlete_id,a.template_id,a.measurements,
                              a.recorded_by,a.assessed_at,a.created_at
                       FROM kaizo_assessments a
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                         AND a.athlete_id=%s AND a.assessment_id=%s""",
                    (tenant_id, coach_actor_id, athlete_id, assessment_id),
                )
                row = cur.fetchone()
        return _assessment(row) if row else None
    if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id):
        return None
    record = _MEMORY_ASSESSMENTS.get(assessment_id)
    return record if record and record["athlete_id"] == athlete_id else None


def create_kpi_definition(*, tenant_id: str, coach_actor_id: str, kpi_id: str,
                          name: str, metric_name: str, unit: str,
                          target: float | None, direction: str) -> dict[str, Any]:
    kpi_id, name, metric_name, unit = (
        str(kpi_id or "").strip(), str(name or "").strip(),
        str(metric_name or "").strip(), str(unit or "").strip(),
    )
    if not all((kpi_id, name, metric_name, unit)):
        raise ValueError("kpi_id, name, metric_name and unit are required")
    if direction not in _ALLOWED_KPI_DIRECTIONS:
        raise ValueError("invalid KPI direction")
    if target is not None and not math.isfinite(float(target)):
        raise ValueError("target must be finite")
    now = _now()
    record = {
        "kpi_id": kpi_id, "name": name, "metric_name": metric_name, "unit": unit,
        "target": target, "direction": direction, "status": "ACTIVE",
        "created_at": now, "updated_at": now,
    }
    if persistence.is_postgres_enabled():
        _ensure_kpi_schema()
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO kaizo_coach_kpi_definitions
                       (tenant_id,coach_actor_id,kpi_id,name,metric_name,unit,target,direction,status,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s)
                       ON CONFLICT (tenant_id,coach_actor_id,kpi_id) DO NOTHING""",
                    (tenant_id, coach_actor_id, kpi_id, name, metric_name, unit,
                     target, direction, now, now),
                )
                if cur.rowcount != 1:
                    raise CoachWorkflowConflict("KPI definition already exists in this Coach scope")
                _audit(
                    tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    action="COACH_KPI_DEFINED", old_value=None, new_value=record,
                    why="KPI definition created in the verified Coach tenant scope.",
                    timestamp=now,
                )
    else:
        key = (tenant_id, coach_actor_id, kpi_id)
        if key in _MEMORY_KPI_DEFINITIONS:
            raise CoachWorkflowConflict("KPI definition already exists in this Coach scope")
        _MEMORY_KPI_DEFINITIONS[key] = record
        _audit(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            action="COACH_KPI_DEFINED", old_value=None, new_value=record,
            why="KPI definition created in the verified Coach tenant scope.",
            timestamp=now,
        )
    return record


def get_kpi_definition(*, tenant_id: str, coach_actor_id: str,
                       kpi_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        _ensure_kpi_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT kpi_id,name,metric_name,unit,target,direction,status,created_at,updated_at
                       FROM kaizo_coach_kpi_definitions
                       WHERE tenant_id=%s AND coach_actor_id=%s AND kpi_id=%s""",
                    (tenant_id, coach_actor_id, kpi_id),
                )
                row = cur.fetchone()
        return _kpi_definition(row) if row else None
    return _MEMORY_KPI_DEFINITIONS.get((tenant_id, coach_actor_id, kpi_id))


def create_kpi_capture(*, tenant_id: str, coach_actor_id: str, athlete_id: str,
                       kpi_id: str, value: float, assessment_id: str | None = None) -> dict[str, Any] | None:
    if not math.isfinite(float(value)):
        raise ValueError("KPI value must be finite")
    now = _now()
    record = {
        "capture_id": str(uuid.uuid4()), "athlete_id": athlete_id,
        "kpi_id": kpi_id, "value": float(value), "captured_by": coach_actor_id,
        "assessment_id": assessment_id, "captured_at": now, "created_at": now,
    }
    if persistence.is_postgres_enabled():
        _ensure_kpi_schema()
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                if not _lock_owned(cur, tenant_id=tenant_id,
                                   coach_actor_id=coach_actor_id, athlete_id=athlete_id):
                    return None
                cur.execute(
                    """SELECT 1 FROM kaizo_coach_kpi_definitions
                       WHERE tenant_id=%s AND coach_actor_id=%s AND kpi_id=%s""",
                    (tenant_id, coach_actor_id, kpi_id),
                )
                if cur.fetchone() is None:
                    raise CoachWorkflowNotFound("KPI definition not found in Coach scope")
                if assessment_id:
                    cur.execute(
                        """SELECT 1 FROM kaizo_assessments
                           WHERE assessment_id=%s AND athlete_id=%s""",
                        (assessment_id, athlete_id),
                    )
                    if cur.fetchone() is None:
                        raise CoachWorkflowNotFound("assessment not found in athlete scope")
                cur.execute(
                    """INSERT INTO kaizo_kpi_captures
                       (capture_id,athlete_id,kpi_id,value,captured_by,assessment_id,captured_at,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["capture_id"], athlete_id, kpi_id, record["value"],
                     coach_actor_id, assessment_id, now, now),
                )
                _audit(
                    tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    action="COACH_KPI_CAPTURED", old_value=None, new_value=record,
                    why="KPI value captured for a currently owned athlete and Coach-scoped KPI.",
                    timestamp=now,
                )
    else:
        if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id):
            return None
        if get_kpi_definition(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                              kpi_id=kpi_id) is None:
            raise CoachWorkflowNotFound("KPI definition not found in Coach scope")
        if assessment_id:
            assessment = get_assessment(
                tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                athlete_id=athlete_id, assessment_id=assessment_id,
            )
            if assessment is None:
                raise CoachWorkflowNotFound("assessment not found in athlete scope")
        _MEMORY_KPI_CAPTURES[record["capture_id"]] = record
        _audit(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            action="COACH_KPI_CAPTURED", old_value=None, new_value=record,
            why="KPI value captured for a currently owned athlete and Coach-scoped KPI.",
            timestamp=now,
        )
    return record


def get_kpi_capture(*, tenant_id: str, coach_actor_id: str, athlete_id: str,
                    capture_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        _ensure_kpi_schema()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT c.capture_id,c.athlete_id,c.kpi_id,c.value,c.captured_by,
                              c.assessment_id,c.captured_at,c.created_at
                       FROM kaizo_kpi_captures c
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=c.athlete_id
                       JOIN kaizo_coach_kpi_definitions k
                         ON k.kpi_id=c.kpi_id AND k.tenant_id=o.tenant_id
                        AND k.coach_actor_id=o.coach_actor_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                         AND c.athlete_id=%s AND c.capture_id=%s""",
                    (tenant_id, coach_actor_id, athlete_id, capture_id),
                )
                row = cur.fetchone()
        return _kpi_capture(row) if row else None
    if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id):
        return None
    record = _MEMORY_KPI_CAPTURES.get(capture_id)
    if not record or record["athlete_id"] != athlete_id:
        return None
    if get_kpi_definition(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                          kpi_id=record["kpi_id"]) is None:
        return None
    return record


def attach_assessment_evidence(*, tenant_id: str, coach_actor_id: str,
                               athlete_id: str, assessment_id: str,
                               evidence_id: str) -> dict[str, Any] | None:
    evidence_id = str(evidence_id or "").strip()
    if not evidence_id:
        raise ValueError("evidence_id is required")
    now = _now()
    record = {
        "assessment_id": assessment_id, "evidence_id": evidence_id,
        "attached_by": coach_actor_id, "attached_at": now,
    }
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                if not _lock_owned(cur, tenant_id=tenant_id,
                                   coach_actor_id=coach_actor_id, athlete_id=athlete_id):
                    return None
                cur.execute(
                    """SELECT 1 FROM kaizo_assessments
                       WHERE assessment_id=%s AND athlete_id=%s""",
                    (assessment_id, athlete_id),
                )
                if cur.fetchone() is None:
                    raise CoachWorkflowNotFound("assessment not found in athlete scope")
                cur.execute(
                    """SELECT 1 FROM kaizo_evidence_records
                       WHERE evidence_id=%s AND subject_type='assessment' AND subject_id=%s""",
                    (evidence_id, assessment_id),
                )
                if cur.fetchone() is None:
                    raise CoachWorkflowNotFound("evidence not found for this assessment")
                cur.execute(
                    """INSERT INTO kaizo_assessment_evidence_attachments
                       (assessment_id,evidence_id,attached_by,attached_at)
                       VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (assessment_id, evidence_id, coach_actor_id, now),
                )
                if cur.rowcount != 1:
                    raise CoachWorkflowConflict("evidence is already attached to this assessment")
                _audit(
                    tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    action="COACH_ASSESSMENT_EVIDENCE_ATTACHED", old_value=None,
                    new_value=record,
                    why="Evidence attached to a verified Coach-owned assessment.",
                    timestamp=now,
                )
    else:
        if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id):
            return None
        assessment = get_assessment(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, assessment_id=assessment_id,
        )
        evidence = _MEMORY_EVIDENCE.get(evidence_id)
        if assessment is None:
            raise CoachWorkflowNotFound("assessment not found in athlete scope")
        if not evidence or evidence.get("subject_type") != "assessment" or evidence.get("subject_id") != assessment_id:
            raise CoachWorkflowNotFound("evidence not found for this assessment")
        key = (assessment_id, evidence_id)
        if key in _MEMORY_ATTACHMENTS:
            raise CoachWorkflowConflict("evidence is already attached to this assessment")
        _MEMORY_ATTACHMENTS[key] = record
        _audit(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            action="COACH_ASSESSMENT_EVIDENCE_ATTACHED", old_value=None,
            new_value=record,
            why="Evidence attached to a verified Coach-owned assessment.",
            timestamp=now,
        )
    return record


def list_assessment_evidence(*, tenant_id: str, coach_actor_id: str,
                             athlete_id: str, assessment_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT x.assessment_id,x.evidence_id,x.attached_by,x.attached_at
                       FROM kaizo_assessment_evidence_attachments x
                       JOIN kaizo_assessments a ON a.assessment_id=x.assessment_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
                       JOIN kaizo_evidence_records e
                         ON e.evidence_id=x.evidence_id AND e.subject_type='assessment'
                        AND e.subject_id=a.assessment_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                         AND a.athlete_id=%s AND a.assessment_id=%s
                       ORDER BY x.attached_at,x.evidence_id""",
                    (tenant_id, coach_actor_id, athlete_id, assessment_id),
                )
                rows = cur.fetchall()
        if get_assessment(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                          athlete_id=athlete_id, assessment_id=assessment_id) is None:
            return None
        return [
            {"assessment_id": r[0], "evidence_id": r[1],
             "attached_by": r[2], "attached_at": r[3]} for r in rows
        ]
    if get_assessment(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                      athlete_id=athlete_id, assessment_id=assessment_id) is None:
        return None
    return sorted(
        [v for (aid, _), v in _MEMORY_ATTACHMENTS.items() if aid == assessment_id],
        key=lambda x: (x["attached_at"], x["evidence_id"]),
    )


def create_state_snapshot(*, tenant_id: str, coach_actor_id: str, athlete_id: str,
                          assessment_id: str, snapshot_type: str,
                          kpi_capture_ids: list[str]) -> dict[str, Any] | None:
    if snapshot_type not in _ALLOWED_SNAPSHOT_TYPES:
        raise ValueError("snapshot_type must be baseline or current_state")
    if not isinstance(kpi_capture_ids, list) or not kpi_capture_ids:
        raise ValueError("at least one KPI capture is required")
    if len(set(kpi_capture_ids)) != len(kpi_capture_ids):
        raise ValueError("duplicate KPI capture IDs are not allowed")
    now = _now()
    snapshot_id = str(uuid.uuid4())
    if persistence.is_postgres_enabled():
        _ensure_kpi_schema()
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                if not _lock_owned(cur, tenant_id=tenant_id,
                                   coach_actor_id=coach_actor_id, athlete_id=athlete_id):
                    return None
                cur.execute(
                    """SELECT measurements FROM kaizo_assessments
                       WHERE assessment_id=%s AND athlete_id=%s""",
                    (assessment_id, athlete_id),
                )
                assessment_row = cur.fetchone()
                if assessment_row is None:
                    raise CoachWorkflowNotFound("assessment not found in athlete scope")
                kpis = []
                for capture_id in kpi_capture_ids:
                    cur.execute(
                        """SELECT c.capture_id,c.kpi_id,c.value,c.assessment_id,
                                  k.name,k.metric_name,k.unit,k.target,k.direction
                           FROM kaizo_kpi_captures c
                           JOIN kaizo_coach_kpi_definitions k
                             ON k.kpi_id=c.kpi_id AND k.tenant_id=%s AND k.coach_actor_id=%s
                           WHERE c.capture_id=%s AND c.athlete_id=%s""",
                        (tenant_id, coach_actor_id, capture_id, athlete_id),
                    )
                    row = cur.fetchone()
                    if row is None:
                        raise CoachWorkflowNotFound("KPI capture not found in athlete and Coach scope")
                    if row[3] is not None and row[3] != assessment_id:
                        raise ValueError("KPI capture belongs to a different assessment")
                    kpis.append({
                        "capture_id": row[0], "kpi_id": row[1], "value": row[2],
                        "assessment_id": row[3], "name": row[4], "metric_name": row[5],
                        "unit": row[6], "target": row[7], "direction": row[8],
                    })
                record = {
                    "snapshot_id": snapshot_id, "athlete_id": athlete_id,
                    "assessment_id": assessment_id, "snapshot_type": snapshot_type,
                    "measurements": assessment_row[0], "kpis": kpis,
                    "captured_by": coach_actor_id, "captured_at": now, "created_at": now,
                }
                cur.execute(
                    """INSERT INTO kaizo_state_snapshots
                       (snapshot_id,athlete_id,assessment_id,snapshot_type,measurements,kpis,captured_by,captured_at,created_at)
                       VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)""",
                    (snapshot_id, athlete_id, assessment_id, snapshot_type,
                     json.dumps(record["measurements"]), json.dumps(kpis),
                     coach_actor_id, now, now),
                )
                _audit(
                    tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    action="COACH_STATE_SNAPSHOT_CREATED", old_value=None,
                    new_value=record,
                    why="Baseline/current state snapshot materialized from owned assessment and KPI captures.",
                    timestamp=now,
                )
    else:
        if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id):
            return None
        assessment = get_assessment(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, assessment_id=assessment_id,
        )
        if assessment is None:
            raise CoachWorkflowNotFound("assessment not found in athlete scope")
        kpis = []
        for capture_id in kpi_capture_ids:
            capture = get_kpi_capture(
                tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                athlete_id=athlete_id, capture_id=capture_id,
            )
            if capture is None:
                raise CoachWorkflowNotFound("KPI capture not found in athlete and Coach scope")
            if capture.get("assessment_id") not in (None, assessment_id):
                raise ValueError("KPI capture belongs to a different assessment")
            definition = get_kpi_definition(
                tenant_id=tenant_id, coach_actor_id=coach_actor_id, kpi_id=capture["kpi_id"]
            )
            kpis.append({
                **capture, "name": definition["name"], "metric_name": definition["metric_name"],
                "unit": definition["unit"], "target": definition["target"],
                "direction": definition["direction"],
            })
        record = {
            "snapshot_id": snapshot_id, "athlete_id": athlete_id,
            "assessment_id": assessment_id, "snapshot_type": snapshot_type,
            "measurements": assessment["measurements"], "kpis": kpis,
            "captured_by": coach_actor_id, "captured_at": now, "created_at": now,
        }
        _MEMORY_SNAPSHOTS[snapshot_id] = record
        _audit(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            action="COACH_STATE_SNAPSHOT_CREATED", old_value=None,
            new_value=record,
            why="Baseline/current state snapshot materialized from owned assessment and KPI captures.",
            timestamp=now,
        )
    return record


def list_state_snapshots(*, tenant_id: str, coach_actor_id: str,
                         athlete_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_coach_athlete_ownership
                       WHERE athlete_id=%s AND tenant_id=%s AND coach_actor_id=%s""",
                    (athlete_id, tenant_id, coach_actor_id),
                )
                if cur.fetchone() is None:
                    return None
                cur.execute(
                    """SELECT s.snapshot_id,s.athlete_id,s.assessment_id,s.snapshot_type,
                              s.measurements,s.kpis,s.captured_by,s.captured_at,s.created_at
                       FROM kaizo_state_snapshots s
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=s.athlete_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                         AND s.athlete_id=%s AND s.captured_by=%s
                       ORDER BY s.created_at DESC,s.snapshot_id""",
                    (tenant_id, coach_actor_id, athlete_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [_snapshot(row) for row in rows]
    if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id):
        return None
    return sorted(
        [record for record in _MEMORY_SNAPSHOTS.values()
         if record.get("athlete_id") == athlete_id
         and record.get("captured_by") == coach_actor_id],
        key=lambda record: (record.get("created_at", ""), record.get("snapshot_id", "")),
        reverse=True,
    )


def get_state_snapshot(*, tenant_id: str, coach_actor_id: str, athlete_id: str,
                       snapshot_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT s.snapshot_id,s.athlete_id,s.assessment_id,s.snapshot_type,
                              s.measurements,s.kpis,s.captured_by,s.captured_at,s.created_at
                       FROM kaizo_state_snapshots s
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=s.athlete_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                         AND s.athlete_id=%s AND s.snapshot_id=%s
                         AND s.captured_by=%s""",
                    (tenant_id, coach_actor_id, athlete_id, snapshot_id, coach_actor_id),
                )
                row = cur.fetchone()
        return _snapshot(row) if row else None
    if not _owned_in_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id):
        return None
    record = _MEMORY_SNAPSHOTS.get(snapshot_id)
    return record if record and record["athlete_id"] == athlete_id and record.get("captured_by") == coach_actor_id else None
