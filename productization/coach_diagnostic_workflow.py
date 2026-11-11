"""Protected Coach cause/context and evidence-linked diagnosis workflows.

FEAT-018–020. Every read/write is bound to the verified Coach + tenant +
athlete ownership relation. Writes lock ownership and atomically persist the
domain record with its tenant audit event. No execution authorization is
created by diagnosis or confidence recording.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import persistence
from . import coach_problem_workflow

_MEMORY_FRAMINGS: dict[str, dict[str, Any]] = {}
_MEMORY_DIAGNOSES: dict[str, dict[str, Any]] = {}
_MEMORY_AUDIT: list[dict[str, Any]] = []


class CoachDiagnosticNotFound(LookupError):
    pass


class CoachDiagnosticConflict(RuntimeError):
    pass


def reset_memory_state() -> None:
    _MEMORY_FRAMINGS.clear()
    _MEMORY_DIAGNOSES.clear()
    _MEMORY_AUDIT.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _problem_row(cur: Any, *, tenant_id: str, coach_actor_id: str,
                 athlete_id: str, problem_id: str, lock: bool = False):
    sql = """SELECT p.problem_id,p.athlete_id,p.assessment_id,p.statement
             FROM kaizo_problem_statements p
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=p.athlete_id
             WHERE o.tenant_id=%s AND o.coach_actor_id=%s
               AND p.athlete_id=%s AND p.problem_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o"
    cur.execute(sql, (tenant_id, coach_actor_id, athlete_id, problem_id))
    return cur.fetchone()


def _memory_problem(*, tenant_id: str, coach_actor_id: str,
                    athlete_id: str, problem_id: str):
    return coach_problem_workflow.get_problem_statement(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, problem_id=problem_id,
    )


def _audit(*, tenant_id: str, coach_actor_id: str, action: str,
           record: dict[str, Any], why: str, timestamp: str) -> None:
    if persistence.is_postgres_enabled():
        persistence.append_tenant_audit(
            tenant_id=tenant_id, timestamp=timestamp, who=coach_actor_id,
            action=action, old_value=None, new_value=record, why=why,
        )
    else:
        _MEMORY_AUDIT.append({
            "tenant_id": tenant_id, "who": coach_actor_id,
            "action": action, "new_value": record, "timestamp": timestamp,
            "why": why,
        })


def create_cause_context_framing(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, problem_id: str,
    cause: str, context: dict[str, Any] | None = None,
    contributing_factors: list[str] | None = None,
) -> dict[str, Any] | None:
    cause = str(cause or "").strip()
    if not cause:
        raise ValueError("cause is required")
    if context is not None and not isinstance(context, dict):
        raise ValueError("context must be an object")
    if contributing_factors is not None and not isinstance(contributing_factors, list):
        raise ValueError("contributing_factors must be a list")
    factors = [str(x).strip() for x in (contributing_factors or []) if str(x).strip()]
    now = _now()
    record = {
        "framing_id": str(uuid.uuid4()), "problem_id": problem_id,
        "athlete_id": athlete_id, "cause": cause, "context": context or {},
        "contributing_factors": factors, "framed_by": coach_actor_id,
        "framed_at": now,
    }
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                problem = _problem_row(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, problem_id=problem_id, lock=True,
                )
                if problem is None:
                    return None
                record["assessment_id"] = problem[2]
                cur.execute(
                    """INSERT INTO kaizo_cause_context_framings
                       (framing_id,problem_id,athlete_id,assessment_id,cause,context,
                        contributing_factors,framed_by,framed_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)""",
                    (record["framing_id"], problem_id, athlete_id, problem[2], cause,
                     json.dumps(record["context"]), json.dumps(factors),
                     coach_actor_id, now),
                )
            _audit(
                tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                action="COACH_CAUSE_CONTEXT_FRAMED", record=record, timestamp=now,
                why="Cause/context framing recorded under verified Coach ownership.",
            )
    else:
        problem = _memory_problem(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, problem_id=problem_id,
        )
        if problem is None:
            return None
        record["assessment_id"] = problem["assessment_id"]
        _MEMORY_FRAMINGS[record["framing_id"]] = record
        _audit(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            action="COACH_CAUSE_CONTEXT_FRAMED", record=record, timestamp=now,
            why="Cause/context framing recorded under verified Coach ownership.",
        )
    return record


def list_cause_context_framings(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, problem_id: str,
) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _problem_row(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id, problem_id=problem_id) is None:
                    return None
                cur.execute(
                    """SELECT f.framing_id,f.problem_id,f.athlete_id,f.assessment_id,
                              f.cause,f.context,f.contributing_factors,f.framed_by,f.framed_at
                       FROM kaizo_cause_context_framings f
                       JOIN kaizo_problem_statements p ON p.problem_id=f.problem_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=p.athlete_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                         AND p.athlete_id=%s AND p.problem_id=%s
                       ORDER BY f.framed_at,f.framing_id""",
                    (tenant_id, coach_actor_id, athlete_id, problem_id),
                )
                rows = cur.fetchall()
        return [{
            "framing_id": r[0], "problem_id": r[1], "athlete_id": r[2],
            "assessment_id": r[3], "cause": r[4], "context": r[5],
            "contributing_factors": r[6], "framed_by": r[7], "framed_at": r[8],
        } for r in rows]
    problem = _memory_problem(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                              athlete_id=athlete_id, problem_id=problem_id)
    if problem is None:
        return None
    return sorted(
        [x for x in _MEMORY_FRAMINGS.values() if x["problem_id"] == problem_id],
        key=lambda x: (x["framed_at"], x["framing_id"]),
    )


def _validate_evidence(cur: Any, *, evidence_id: str,
                       athlete_id: str, problem_id: str, assessment_id: str):
    cur.execute(
        """SELECT evidence_id,subject_type,subject_id,evidence_level,status,
                  source_ref,claim,observed_value,verified_by,verified_at,notes
           FROM kaizo_evidence_records WHERE evidence_id=%s FOR SHARE""",
        (evidence_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise CoachDiagnosticNotFound(f"evidence not found: {evidence_id}")
    subject_type = str(row[1] or "").strip().lower()
    subject_id = str(row[2] or "").strip()
    allowed_subjects = {
        ("assessment", assessment_id),
        ("problem_statement", problem_id),
        ("problem", problem_id),
        ("athlete", athlete_id),
    }
    if (subject_type, subject_id) not in allowed_subjects:
        raise CoachDiagnosticConflict(
            f"evidence is not linked to this athlete/problem/assessment: {evidence_id}"
        )
    status = str(row[4] or "").strip().upper()
    level = str(row[3] or "").strip().upper()
    if status != "VERIFIED":
        raise CoachDiagnosticConflict(f"evidence is not verified: {evidence_id}")
    if level == "E0":
        raise CoachDiagnosticConflict(f"E0 evidence cannot support diagnosis: {evidence_id}")
    return {
        "evidence_id": row[0], "subject_type": row[1], "subject_id": row[2],
        "evidence_level": row[3], "status": row[4], "source_ref": row[5],
        "claim": row[6], "observed_value": row[7], "verified_by": row[8],
        "verified_at": row[9], "notes": row[10],
    }


def create_evidence_linked_diagnosis(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, problem_id: str,
    evidence_ids: list[str], diagnosis: str, confidence: str | None = None,
    resolution_state: str = "UNRESOLVED",
) -> dict[str, Any] | None:
    diagnosis = str(diagnosis or "").strip()
    evidence_ids = list(dict.fromkeys(str(x).strip() for x in (evidence_ids or []) if str(x).strip()))
    confidence = str(confidence).upper().strip() if confidence is not None else None
    resolution_state = str(resolution_state or "UNRESOLVED").upper().strip()
    if not diagnosis:
        raise ValueError("diagnosis is required")
    if not evidence_ids:
        raise ValueError("at least one evidence_id is required")
    if confidence not in {None, "LOW", "MEDIUM", "HIGH"}:
        raise ValueError("confidence must be LOW, MEDIUM, or HIGH")
    if resolution_state not in {"UNRESOLVED", "RESOLVED"}:
        raise ValueError("resolution_state must be UNRESOLVED or RESOLVED")
    now = _now()
    record = {
        "diagnosis_id": str(uuid.uuid4()), "problem_id": problem_id,
        "athlete_id": athlete_id, "evidence_ids": evidence_ids,
        "diagnosis": diagnosis, "diagnosed_by": coach_actor_id,
        "confidence": confidence, "resolution_state": resolution_state,
        "diagnosed_at": now,
    }
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                problem = _problem_row(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, problem_id=problem_id, lock=True,
                )
                if problem is None:
                    return None
                record["assessment_id"] = problem[2]
                for evidence_id in evidence_ids:
                    _validate_evidence(
                        cur, evidence_id=evidence_id, athlete_id=athlete_id,
                        problem_id=problem_id, assessment_id=problem[2],
                    )
                cur.execute(
                    """INSERT INTO kaizo_evidence_linked_diagnoses
                       (diagnosis_id,problem_id,athlete_id,assessment_id,evidence_ids,
                        diagnosis,diagnosed_by,confidence,resolution_state,diagnosed_at)
                       VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s)""",
                    (record["diagnosis_id"], problem_id, athlete_id, problem[2],
                     json.dumps(evidence_ids), diagnosis, coach_actor_id, confidence,
                     resolution_state, now),
                )
            _audit(
                tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                action="COACH_EVIDENCE_LINKED_DIAGNOSIS_CREATED", record=record,
                timestamp=now,
                why="Diagnosis linked to verified non-E0 evidence in the same owned athlete scope.",
            )
    else:
        problem = _memory_problem(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, problem_id=problem_id)
        if problem is None:
            return None
        record["assessment_id"] = problem["assessment_id"]
        for evidence_id in evidence_ids:
            evidence = persistence.get_evidence(evidence_id)
            if evidence is None:
                raise CoachDiagnosticNotFound(f"evidence not found: {evidence_id}")
            subject = (str(evidence.get("subject_type") or "").lower(),
                       str(evidence.get("subject_id") or ""))
            if subject not in {
                ("assessment", problem["assessment_id"]),
                ("problem_statement", problem_id), ("problem", problem_id),
                ("athlete", athlete_id),
            }:
                raise CoachDiagnosticConflict(f"evidence is outside this athlete scope: {evidence_id}")
            if str(evidence.get("status") or "").upper() != "VERIFIED":
                raise CoachDiagnosticConflict(f"evidence is not verified: {evidence_id}")
            if str(evidence.get("evidence_level") or "").upper() == "E0":
                raise CoachDiagnosticConflict(f"E0 evidence cannot support diagnosis: {evidence_id}")
        _MEMORY_DIAGNOSES[record["diagnosis_id"]] = record
        _audit(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            action="COACH_EVIDENCE_LINKED_DIAGNOSIS_CREATED", record=record,
            timestamp=now,
            why="Diagnosis linked to verified non-E0 evidence in the same owned athlete scope.",
        )
    return record


def list_evidence_linked_diagnoses(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, problem_id: str,
) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _problem_row(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id, problem_id=problem_id) is None:
                    return None
                cur.execute(
                    """SELECT d.diagnosis_id,d.problem_id,d.athlete_id,d.assessment_id,
                              d.evidence_ids,d.diagnosis,d.diagnosed_by,d.confidence,
                              d.resolution_state,d.diagnosed_at
                       FROM kaizo_evidence_linked_diagnoses d
                       JOIN kaizo_problem_statements p ON p.problem_id=d.problem_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=p.athlete_id
                       WHERE o.tenant_id=%s AND o.coach_actor_id=%s
                         AND p.athlete_id=%s AND p.problem_id=%s
                       ORDER BY d.diagnosed_at,d.diagnosis_id""",
                    (tenant_id, coach_actor_id, athlete_id, problem_id),
                )
                rows = cur.fetchall()
        return [{
            "diagnosis_id": r[0], "problem_id": r[1], "athlete_id": r[2],
            "assessment_id": r[3], "evidence_ids": r[4], "diagnosis": r[5],
            "diagnosed_by": r[6], "confidence": r[7],
            "resolution_state": r[8], "diagnosed_at": r[9],
        } for r in rows]
    problem = _memory_problem(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                              athlete_id=athlete_id, problem_id=problem_id)
    if problem is None:
        return None
    return sorted(
        [x for x in _MEMORY_DIAGNOSES.values() if x["problem_id"] == problem_id],
        key=lambda x: (x["diagnosed_at"], x["diagnosis_id"]),
    )
