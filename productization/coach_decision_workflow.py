"""Protected Coach decision candidate, rationale, comparison, review and record workflows.

FEAT-021–025. All decision records inherit the verified Coach/tenant/athlete
scope from the source diagnosis. The Coach is the only final authority and
recording a decision never authorizes execution.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import persistence
from . import coach_diagnostic_workflow


_MEMORY_CANDIDATES: dict[str, dict[str, Any]] = {}
_MEMORY_RATIONALES: dict[str, dict[str, Any]] = {}
_MEMORY_COMPARISONS: dict[str, dict[str, Any]] = {}
_MEMORY_REVIEWS: dict[str, dict[str, Any]] = {}
_MEMORY_DECISIONS: dict[str, dict[str, Any]] = {}
_MEMORY_AUDIT: list[dict[str, Any]] = []

_CANDIDATE_SPECS = (
    ("DIRECT_INTERVENTION", "Directly address the diagnosed issue",
     "Targets the diagnosed issue while preserving Coach review before execution."),
    ("CONSTRAINT_ADJUSTMENT", "Adjust the training constraint",
     "Changes the task constraint related to the diagnosis for Coach consideration."),
    ("RETEST_FOCUSED", "Use a focused retest before commitment",
     "Generates a verification-oriented candidate to test the diagnosis before a stronger intervention."),
)


class CoachDecisionNotFound(LookupError):
    pass


class CoachDecisionConflict(RuntimeError):
    pass


def reset_memory_state() -> None:
    for store in (_MEMORY_CANDIDATES, _MEMORY_RATIONALES, _MEMORY_COMPARISONS,
                  _MEMORY_REVIEWS, _MEMORY_DECISIONS):
        store.clear()
    _MEMORY_AUDIT.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(*, tenant_id: str, coach_actor_id: str, action: str,
           record: dict[str, Any], why: str, timestamp: str) -> None:
    if persistence.is_postgres_enabled():
        persistence.append_tenant_audit(
            tenant_id=tenant_id, timestamp=timestamp, who=coach_actor_id,
            action=action, old_value=None, new_value=record, why=why,
        )
    else:
        _MEMORY_AUDIT.append({
            "tenant_id": tenant_id, "who": coach_actor_id, "action": action,
            "new_value": record, "timestamp": timestamp, "why": why,
        })


def _diagnosis_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
                   athlete_id: str, diagnosis_id: str, lock: bool = False):
    sql = """SELECT d.diagnosis_id,d.problem_id,d.athlete_id,d.assessment_id,
                    d.evidence_ids,d.diagnosis,d.diagnosed_by,d.confidence,
                    d.resolution_state,d.diagnosed_at
             FROM kaizo_evidence_linked_diagnoses d
             JOIN kaizo_problem_statements p
               ON p.problem_id=d.problem_id AND p.athlete_id=d.athlete_id
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=d.athlete_id
             WHERE d.diagnosis_id=%s AND d.athlete_id=%s
               AND o.tenant_id=%s AND o.coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o,d"
    cur.execute(sql, (diagnosis_id, athlete_id, tenant_id, coach_actor_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "diagnosis_id": row[0], "problem_id": row[1], "athlete_id": row[2],
        "assessment_id": row[3], "evidence_ids": row[4], "diagnosis": row[5],
        "diagnosed_by": row[6], "confidence": row[7],
        "resolution_state": row[8], "diagnosed_at": row[9],
    }


def _memory_diagnosis(*, tenant_id: str, coach_actor_id: str,
                      athlete_id: str, diagnosis_id: str):
    diagnosis = coach_diagnostic_workflow._MEMORY_DIAGNOSES.get(diagnosis_id)
    if diagnosis is None or diagnosis.get("athlete_id") != athlete_id:
        return None
    problem = coach_diagnostic_workflow._memory_problem(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, problem_id=diagnosis["problem_id"],
    )
    return diagnosis if problem is not None else None


def _candidate_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
                   athlete_id: str, candidate_id: str, lock: bool = False):
    sql = """SELECT c.candidate_id,c.diagnosis_id,c.problem_id,c.athlete_id,
                    c.assessment_id,c.candidate_type,c.title,c.rationale,
                    c.source_diagnosis,c.status,c.generated_by,c.created_at
             FROM kaizo_decision_candidates c
             JOIN kaizo_evidence_linked_diagnoses d
               ON d.diagnosis_id=c.diagnosis_id AND d.athlete_id=c.athlete_id
             JOIN kaizo_problem_statements p
               ON p.problem_id=c.problem_id AND p.athlete_id=c.athlete_id
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=c.athlete_id
             WHERE c.candidate_id=%s AND c.athlete_id=%s
               AND o.tenant_id=%s AND o.coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o,c"
    cur.execute(sql, (candidate_id, athlete_id, tenant_id, coach_actor_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "candidate_id": row[0], "diagnosis_id": row[1], "problem_id": row[2],
        "athlete_id": row[3], "assessment_id": row[4], "candidate_type": row[5],
        "title": row[6], "rationale": row[7], "source_diagnosis": row[8],
        "status": row[9], "generated_by": row[10], "created_at": row[11],
    }


def _memory_candidate(*, tenant_id: str, coach_actor_id: str,
                      athlete_id: str, candidate_id: str):
    candidate = _MEMORY_CANDIDATES.get(candidate_id)
    if candidate is None or candidate.get("athlete_id") != athlete_id:
        return None
    diagnosis = _memory_diagnosis(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, diagnosis_id=candidate["diagnosis_id"],
    )
    return candidate if diagnosis is not None else None


def _evidence_sql(cur: Any, *, evidence_id: str, athlete_id: str,
                  problem_id: str, assessment_id: str):
    cur.execute(
        """SELECT evidence_id,subject_type,subject_id,evidence_level,status
           FROM kaizo_evidence_records WHERE evidence_id=%s FOR SHARE""",
        (evidence_id,),
    )
    row = cur.fetchone()
    if row is None:
        raise CoachDecisionNotFound(f"evidence not found: {evidence_id}")
    subject = (str(row[1] or "").strip().lower(), str(row[2] or "").strip())
    if subject not in {
        ("assessment", assessment_id), ("problem_statement", problem_id),
        ("problem", problem_id), ("athlete", athlete_id),
    }:
        raise CoachDecisionConflict(f"evidence is outside this athlete/problem scope: {evidence_id}")
    if str(row[4] or "").strip().upper() != "VERIFIED":
        raise CoachDecisionConflict(f"evidence is not verified: {evidence_id}")
    if str(row[3] or "").strip().upper() == "E0":
        raise CoachDecisionConflict(f"E0 evidence cannot support a decision: {evidence_id}")


def _evidence_memory(*, evidence_id: str, athlete_id: str,
                     problem_id: str, assessment_id: str):
    evidence = persistence.get_evidence(evidence_id)
    if evidence is None:
        raise CoachDecisionNotFound(f"evidence not found: {evidence_id}")
    subject = (str(evidence.get("subject_type") or "").strip().lower(),
               str(evidence.get("subject_id") or "").strip())
    if subject not in {
        ("assessment", assessment_id), ("problem_statement", problem_id),
        ("problem", problem_id), ("athlete", athlete_id),
    }:
        raise CoachDecisionConflict(f"evidence is outside this athlete/problem scope: {evidence_id}")
    if str(evidence.get("status") or "").strip().upper() != "VERIFIED":
        raise CoachDecisionConflict(f"evidence is not verified: {evidence_id}")
    if str(evidence.get("evidence_level") or "").strip().upper() == "E0":
        raise CoachDecisionConflict(f"E0 evidence cannot support a decision: {evidence_id}")


def _revalidate_diagnosis_evidence_sql(cur: Any, diagnosis: dict[str, Any], athlete_id: str) -> None:
    for evidence_id in diagnosis.get("evidence_ids") or []:
        _evidence_sql(
            cur, evidence_id=evidence_id, athlete_id=athlete_id,
            problem_id=diagnosis["problem_id"], assessment_id=diagnosis["assessment_id"],
        )


def _revalidate_diagnosis_evidence_memory(diagnosis: dict[str, Any], athlete_id: str) -> None:
    for evidence_id in diagnosis.get("evidence_ids") or []:
        _evidence_memory(
            evidence_id=evidence_id, athlete_id=athlete_id,
            problem_id=diagnosis["problem_id"], assessment_id=diagnosis["assessment_id"],
        )


def generate_decision_candidates(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, diagnosis_id: str,
) -> dict[str, Any] | None:
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                diagnosis = _diagnosis_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, diagnosis_id=diagnosis_id, lock=True,
                )
                if diagnosis is None:
                    return None
                for evidence_id in diagnosis["evidence_ids"] or []:
                    _evidence_sql(
                        cur, evidence_id=evidence_id, athlete_id=athlete_id,
                        problem_id=diagnosis["problem_id"],
                        assessment_id=diagnosis["assessment_id"],
                    )
                cur.execute(
                    """SELECT candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                              candidate_type,title,rationale,source_diagnosis,status,generated_by,created_at
                       FROM kaizo_decision_candidates WHERE diagnosis_id=%s
                       ORDER BY created_at,candidate_id""",
                    (diagnosis_id,),
                )
                existing = cur.fetchall()
                if existing:
                    candidates = [{
                        "candidate_id": x[0], "diagnosis_id": x[1], "problem_id": x[2],
                        "athlete_id": x[3], "assessment_id": x[4], "candidate_type": x[5],
                        "title": x[6], "rationale": x[7], "source_diagnosis": x[8],
                        "status": x[9], "generated_by": x[10], "created_at": x[11],
                    } for x in existing]
                    return {"diagnosis_id": diagnosis_id, "status": "CANDIDATES_ALREADY_EXIST",
                            "candidates": candidates, "coach_review_required": True}
                candidates = []
                for kind, title, rationale in _CANDIDATE_SPECS:
                    item = {
                        "candidate_id": str(uuid.uuid4()), "diagnosis_id": diagnosis_id,
                        "problem_id": diagnosis["problem_id"], "athlete_id": athlete_id,
                        "assessment_id": diagnosis["assessment_id"], "candidate_type": kind,
                        "title": title, "rationale": rationale,
                        "source_diagnosis": diagnosis["diagnosis"],
                        "status": "PENDING_COACH_REVIEW", "generated_by": coach_actor_id,
                        "created_at": now,
                    }
                    cur.execute(
                        """INSERT INTO kaizo_decision_candidates
                           (candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                            candidate_type,title,rationale,source_diagnosis,status,generated_by,created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (item["candidate_id"], diagnosis_id, item["problem_id"], athlete_id,
                         diagnosis["assessment_id"], kind, title, rationale,
                         diagnosis["diagnosis"], item["status"], coach_actor_id, now),
                    )
                    candidates.append(item)
            _audit(
                tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                action="COACH_DECISION_CANDIDATES_GENERATED",
                record={"diagnosis_id": diagnosis_id, "candidate_ids": [x["candidate_id"] for x in candidates]},
                timestamp=now,
                why="Evidence revalidated and decision candidates generated within verified Coach ownership.",
            )
    else:
        diagnosis = _memory_diagnosis(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, diagnosis_id=diagnosis_id,
        )
        if diagnosis is None:
            return None
        for evidence_id in diagnosis["evidence_ids"]:
            _evidence_memory(
                evidence_id=evidence_id, athlete_id=athlete_id,
                problem_id=diagnosis["problem_id"], assessment_id=diagnosis["assessment_id"],
            )
        existing = [x for x in _MEMORY_CANDIDATES.values() if x["diagnosis_id"] == diagnosis_id]
        if existing:
            return {"diagnosis_id": diagnosis_id, "status": "CANDIDATES_ALREADY_EXIST",
                    "candidates": sorted(existing, key=lambda x: x["candidate_id"]),
                    "coach_review_required": True}
        candidates = []
        for kind, title, rationale in _CANDIDATE_SPECS:
            item = {
                "candidate_id": str(uuid.uuid4()), "diagnosis_id": diagnosis_id,
                "problem_id": diagnosis["problem_id"], "athlete_id": athlete_id,
                "assessment_id": diagnosis["assessment_id"], "candidate_type": kind,
                "title": title, "rationale": rationale,
                "source_diagnosis": diagnosis["diagnosis"],
                "status": "PENDING_COACH_REVIEW", "generated_by": coach_actor_id,
                "created_at": now,
            }
            _MEMORY_CANDIDATES[item["candidate_id"]] = item
            candidates.append(item)
        _audit(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            action="COACH_DECISION_CANDIDATES_GENERATED",
            record={"diagnosis_id": diagnosis_id, "candidate_ids": [x["candidate_id"] for x in candidates]},
            timestamp=now,
            why="Evidence revalidated and decision candidates generated within verified Coach ownership.",
        )
    return {"diagnosis_id": diagnosis_id, "status": "CANDIDATES_GENERATED",
            "candidates": candidates, "coach_review_required": True}


def list_decision_candidates(*, tenant_id: str, coach_actor_id: str,
                              athlete_id: str, diagnosis_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _diagnosis_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, diagnosis_id=diagnosis_id) is None:
                    return None
                cur.execute(
                    """SELECT c.candidate_id,c.diagnosis_id,c.problem_id,c.athlete_id,c.assessment_id,
                              c.candidate_type,c.title,c.rationale,c.source_diagnosis,c.status,c.generated_by,c.created_at
                       FROM kaizo_decision_candidates c
                       JOIN kaizo_evidence_linked_diagnoses d ON d.diagnosis_id=c.diagnosis_id
                       JOIN kaizo_problem_statements p ON p.problem_id=c.problem_id AND p.athlete_id=c.athlete_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=c.athlete_id
                       WHERE c.diagnosis_id=%s AND c.athlete_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY c.created_at,c.candidate_id""",
                    (diagnosis_id, athlete_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "candidate_id": x[0], "diagnosis_id": x[1], "problem_id": x[2],
            "athlete_id": x[3], "assessment_id": x[4], "candidate_type": x[5],
            "title": x[6], "rationale": x[7], "source_diagnosis": x[8],
            "status": x[9], "generated_by": x[10], "created_at": x[11],
        } for x in rows]
    diagnosis = _memory_diagnosis(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, diagnosis_id=diagnosis_id)
    if diagnosis is None:
        return None
    return sorted([x for x in _MEMORY_CANDIDATES.values() if x["diagnosis_id"] == diagnosis_id],
                  key=lambda x: (x["created_at"], x["candidate_id"]))


def record_decision_rationale(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, candidate_id: str,
    rationale: str, evidence_ids: list[str],
) -> dict[str, Any] | None:
    rationale = str(rationale or "").strip()
    evidence_ids = list(dict.fromkeys(str(x).strip() for x in (evidence_ids or []) if str(x).strip()))
    if not rationale:
        raise ValueError("rationale is required")
    if not evidence_ids:
        raise ValueError("at least one evidence_id is required")
    now = _now()
    record = None
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                candidate = _candidate_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, candidate_id=candidate_id, lock=True,
                )
                if candidate is None:
                    return None
                for evidence_id in evidence_ids:
                    _evidence_sql(
                        cur, evidence_id=evidence_id, athlete_id=athlete_id,
                        problem_id=candidate["problem_id"], assessment_id=candidate["assessment_id"],
                    )
                record = {
                    "rationale_id": str(uuid.uuid4()), "candidate_id": candidate_id,
                    "diagnosis_id": candidate["diagnosis_id"], "problem_id": candidate["problem_id"],
                    "athlete_id": athlete_id, "assessment_id": candidate["assessment_id"],
                    "rationale": rationale, "evidence_ids": evidence_ids,
                    "recorded_by": coach_actor_id, "recorded_at": now,
                    "coach_review_required": True,
                }
                cur.execute(
                    """INSERT INTO kaizo_decision_rationales
                       (rationale_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                        rationale,evidence_ids,recorded_by,recorded_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                    (record["rationale_id"], candidate_id, candidate["diagnosis_id"],
                     candidate["problem_id"], athlete_id, candidate["assessment_id"],
                     rationale, json.dumps(evidence_ids), coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_DECISION_RATIONALE_RECORDED", record=record,
                   timestamp=now, why="Evidence-linked rationale recorded within owned Coach scope; review remains required.")
    else:
        candidate = _memory_candidate(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, candidate_id=candidate_id,
        )
        if candidate is None:
            return None
        for evidence_id in evidence_ids:
            _evidence_memory(evidence_id=evidence_id, athlete_id=athlete_id,
                             problem_id=candidate["problem_id"], assessment_id=candidate["assessment_id"])
        record = {
            "rationale_id": str(uuid.uuid4()), "candidate_id": candidate_id,
            "diagnosis_id": candidate["diagnosis_id"], "problem_id": candidate["problem_id"],
            "athlete_id": athlete_id, "assessment_id": candidate["assessment_id"],
            "rationale": rationale, "evidence_ids": evidence_ids,
            "recorded_by": coach_actor_id, "recorded_at": now, "coach_review_required": True,
        }
        _MEMORY_RATIONALES[record["rationale_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_DECISION_RATIONALE_RECORDED", record=record,
               timestamp=now, why="Evidence-linked rationale recorded within owned Coach scope; review remains required.")
    return record


def list_decision_rationales(*, tenant_id: str, coach_actor_id: str,
                             athlete_id: str, candidate_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _candidate_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, candidate_id=candidate_id) is None:
                    return None
                cur.execute(
                    """SELECT r.rationale_id,r.candidate_id,r.diagnosis_id,r.problem_id,r.athlete_id,
                              r.assessment_id,r.rationale,r.evidence_ids,r.recorded_by,r.recorded_at
                       FROM kaizo_decision_rationales r
                       JOIN kaizo_decision_candidates c ON c.candidate_id=r.candidate_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=c.athlete_id
                       WHERE r.candidate_id=%s AND c.athlete_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY r.recorded_at,r.rationale_id""",
                    (candidate_id, athlete_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "rationale_id": x[0], "candidate_id": x[1], "diagnosis_id": x[2],
            "problem_id": x[3], "athlete_id": x[4], "assessment_id": x[5],
            "rationale": x[6], "evidence_ids": x[7], "recorded_by": x[8], "recorded_at": x[9],
            "coach_review_required": True,
        } for x in rows]
    candidate = _memory_candidate(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, candidate_id=candidate_id)
    if candidate is None:
        return None
    return sorted([x for x in _MEMORY_RATIONALES.values() if x["candidate_id"] == candidate_id],
                  key=lambda x: (x["recorded_at"], x["rationale_id"]))


def compare_decision_alternatives(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, diagnosis_id: str,
    candidate_ids: list[str],
) -> dict[str, Any] | None:
    ids = [str(x).strip() for x in (candidate_ids or [])]
    if len(ids) < 2:
        raise ValueError("at least two candidate_ids are required")
    if any(not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError("candidate_ids must be non-empty and distinct")
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                diagnosis = _diagnosis_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, diagnosis_id=diagnosis_id, lock=True,
                )
                if diagnosis is None:
                    return None
                _revalidate_diagnosis_evidence_sql(cur, diagnosis, athlete_id)
                alternatives = []
                for candidate_id in ids:
                    candidate = _candidate_sql(
                        cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                        athlete_id=athlete_id, candidate_id=candidate_id, lock=True,
                    )
                    if candidate is None:
                        raise CoachDecisionNotFound(f"candidate not found in Coach scope: {candidate_id}")
                    if candidate["diagnosis_id"] != diagnosis_id:
                        raise CoachDecisionConflict("all candidates must belong to the selected diagnosis")
                    alternatives.append({k: candidate[k] for k in
                                          ("candidate_id", "candidate_type", "title", "rationale", "status")})
                record = {
                    "comparison_id": str(uuid.uuid4()), "diagnosis_id": diagnosis_id,
                    "candidate_ids": ids, "alternatives": alternatives,
                    "comparison_status": "READY_FOR_COACH_REVIEW",
                    "compared_by": coach_actor_id, "compared_at": now,
                    "coach_review_required": True,
                }
                cur.execute(
                    """INSERT INTO kaizo_decision_comparisons
                       (comparison_id,diagnosis_id,candidate_ids,alternatives,comparison_status,compared_by,compared_at)
                       VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s)""",
                    (record["comparison_id"], diagnosis_id, json.dumps(ids),
                     json.dumps(alternatives), record["comparison_status"], coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_DECISION_ALTERNATIVES_COMPARED", record=record,
                   timestamp=now, why="Alternatives compared for explicit Coach review; no decision or execution issued.")
    else:
        diagnosis = _memory_diagnosis(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                      athlete_id=athlete_id, diagnosis_id=diagnosis_id)
        if diagnosis is None:
            return None
        _revalidate_diagnosis_evidence_memory(diagnosis, athlete_id)
        alternatives = []
        for candidate_id in ids:
            candidate = _memory_candidate(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                          athlete_id=athlete_id, candidate_id=candidate_id)
            if candidate is None:
                raise CoachDecisionNotFound(f"candidate not found in Coach scope: {candidate_id}")
            if candidate["diagnosis_id"] != diagnosis_id:
                raise CoachDecisionConflict("all candidates must belong to the selected diagnosis")
            alternatives.append({k: candidate[k] for k in
                                  ("candidate_id", "candidate_type", "title", "rationale", "status")})
        record = {
            "comparison_id": str(uuid.uuid4()), "diagnosis_id": diagnosis_id,
            "candidate_ids": ids, "alternatives": alternatives,
            "comparison_status": "READY_FOR_COACH_REVIEW",
            "compared_by": coach_actor_id, "compared_at": now,
            "coach_review_required": True,
        }
        _MEMORY_COMPARISONS[record["comparison_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_DECISION_ALTERNATIVES_COMPARED", record=record,
               timestamp=now, why="Alternatives compared for explicit Coach review; no decision or execution issued.")
    return record


def list_decision_comparisons(*, tenant_id: str, coach_actor_id: str,
                              athlete_id: str, diagnosis_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _diagnosis_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, diagnosis_id=diagnosis_id) is None:
                    return None
                cur.execute(
                    """SELECT x.comparison_id,x.diagnosis_id,x.candidate_ids,x.alternatives,
                              x.comparison_status,x.compared_by,x.compared_at
                       FROM kaizo_decision_comparisons x
                       JOIN kaizo_evidence_linked_diagnoses d ON d.diagnosis_id=x.diagnosis_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=d.athlete_id
                       WHERE x.diagnosis_id=%s AND d.athlete_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY x.compared_at,x.comparison_id""",
                    (diagnosis_id, athlete_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "comparison_id": x[0], "diagnosis_id": x[1], "candidate_ids": x[2],
            "alternatives": x[3], "comparison_status": x[4],
            "compared_by": x[5], "compared_at": x[6], "coach_review_required": True,
        } for x in rows]
    diagnosis = _memory_diagnosis(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, diagnosis_id=diagnosis_id)
    if diagnosis is None:
        return None
    return sorted([x for x in _MEMORY_COMPARISONS.values() if x["diagnosis_id"] == diagnosis_id],
                  key=lambda x: (x["compared_at"], x["comparison_id"]))


def review_decision_candidate(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, candidate_id: str,
    action: str, override_reason: str | None = None,
) -> dict[str, Any] | None:
    action = str(action or "").upper().strip()
    reason = str(override_reason or "").strip() or None
    if action not in {"CONFIRM", "OVERRIDE"}:
        raise ValueError("action must be CONFIRM or OVERRIDE")
    if action == "OVERRIDE" and not reason:
        raise ValueError("override_reason is required for OVERRIDE")
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                candidate = _candidate_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, candidate_id=candidate_id, lock=True,
                )
                if candidate is None:
                    return None
                diagnosis = _diagnosis_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, diagnosis_id=candidate["diagnosis_id"], lock=True,
                )
                if diagnosis is None:
                    return None
                _revalidate_diagnosis_evidence_sql(cur, diagnosis, athlete_id)
                record = {
                    "review_id": str(uuid.uuid4()), "candidate_id": candidate_id,
                    "diagnosis_id": candidate["diagnosis_id"], "problem_id": candidate["problem_id"],
                    "athlete_id": athlete_id, "assessment_id": candidate["assessment_id"],
                    "action": action, "status": "COACH_CONFIRMED" if action == "CONFIRM" else "COACH_OVERRIDDEN",
                    "coach_id": coach_actor_id, "override_reason": reason, "reviewed_at": now,
                    "coach_final_authority": True, "execution_authorized": False,
                }
                cur.execute(
                    """INSERT INTO kaizo_coach_decision_reviews
                       (review_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                        action,status,coach_id,override_reason,reviewed_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["review_id"], candidate_id, candidate["diagnosis_id"],
                     candidate["problem_id"], athlete_id, candidate["assessment_id"],
                     action, record["status"], coach_actor_id, reason, now),
                )
                cur.execute("UPDATE kaizo_decision_candidates SET status=%s WHERE candidate_id=%s",
                            (record["status"], candidate_id))
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_DECISION_CANDIDATE_REVIEWED", record=record,
                   timestamp=now, why="Verified Coach explicitly confirmed or overrode the candidate; execution remains disabled.")
    else:
        candidate = _memory_candidate(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                      athlete_id=athlete_id, candidate_id=candidate_id)
        if candidate is None:
            return None
        diagnosis = _memory_diagnosis(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, diagnosis_id=candidate["diagnosis_id"],
        )
        if diagnosis is None:
            return None
        _revalidate_diagnosis_evidence_memory(diagnosis, athlete_id)
        record = {
            "review_id": str(uuid.uuid4()), "candidate_id": candidate_id,
            "diagnosis_id": candidate["diagnosis_id"], "problem_id": candidate["problem_id"],
            "athlete_id": athlete_id, "assessment_id": candidate["assessment_id"],
            "action": action, "status": "COACH_CONFIRMED" if action == "CONFIRM" else "COACH_OVERRIDDEN",
            "coach_id": coach_actor_id, "override_reason": reason, "reviewed_at": now,
            "coach_final_authority": True, "execution_authorized": False,
        }
        candidate["status"] = record["status"]
        _MEMORY_REVIEWS[record["review_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_DECISION_CANDIDATE_REVIEWED", record=record,
               timestamp=now, why="Verified Coach explicitly confirmed or overrode the candidate; execution remains disabled.")
    return record


def list_candidate_reviews(*, tenant_id: str, coach_actor_id: str,
                           athlete_id: str, candidate_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _candidate_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, candidate_id=candidate_id) is None:
                    return None
                cur.execute(
                    """SELECT r.review_id,r.candidate_id,r.diagnosis_id,r.problem_id,r.athlete_id,
                              r.assessment_id,r.action,r.status,r.coach_id,r.override_reason,r.reviewed_at
                       FROM kaizo_coach_decision_reviews r
                       JOIN kaizo_decision_candidates c ON c.candidate_id=r.candidate_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=c.athlete_id
                       WHERE r.candidate_id=%s AND c.athlete_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY r.reviewed_at,r.review_id""",
                    (candidate_id, athlete_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "review_id": x[0], "candidate_id": x[1], "diagnosis_id": x[2],
            "problem_id": x[3], "athlete_id": x[4], "assessment_id": x[5],
            "action": x[6], "status": x[7], "coach_id": x[8],
            "override_reason": x[9], "reviewed_at": x[10],
            "coach_final_authority": True, "execution_authorized": False,
        } for x in rows]
    candidate = _memory_candidate(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, candidate_id=candidate_id)
    if candidate is None:
        return None
    return sorted([x for x in _MEMORY_REVIEWS.values() if x["candidate_id"] == candidate_id],
                  key=lambda x: (x["reviewed_at"], x["review_id"]))


def record_coach_decision(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, candidate_id: str,
    outcome_intent: str, decision_summary: str | None = None,
) -> dict[str, Any] | None:
    outcome_intent = str(outcome_intent or "").strip()
    if not outcome_intent:
        raise ValueError("outcome_intent is required")
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                candidate = _candidate_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, candidate_id=candidate_id, lock=True,
                )
                if candidate is None:
                    return None
                diagnosis = _diagnosis_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, diagnosis_id=candidate["diagnosis_id"], lock=True,
                )
                if diagnosis is None:
                    return None
                _revalidate_diagnosis_evidence_sql(cur, diagnosis, athlete_id)
                cur.execute(
                    """SELECT action FROM kaizo_coach_decision_reviews
                       WHERE candidate_id=%s ORDER BY reviewed_at DESC,review_id DESC LIMIT 1""",
                    (candidate_id,),
                )
                latest = cur.fetchone()
                if latest is None:
                    raise CoachDecisionConflict("Coach confirmation or override is required before recording the decision")
                record = {
                    "decision_id": str(uuid.uuid4()), "candidate_id": candidate_id,
                    "diagnosis_id": candidate["diagnosis_id"], "problem_id": candidate["problem_id"],
                    "athlete_id": athlete_id, "assessment_id": candidate["assessment_id"],
                    "candidate_type": candidate["candidate_type"], "coach_action": latest[0],
                    "coach_id": coach_actor_id,
                    "decision_summary": str(decision_summary or "").strip() or candidate["title"],
                    "outcome_intent": outcome_intent, "status": "RECORDED",
                    "coach_final_authority": True, "execution_authorized": False,
                    "recorded_at": now,
                }
                cur.execute(
                    """INSERT INTO kaizo_decision_records
                       (decision_id,candidate_id,diagnosis_id,problem_id,athlete_id,assessment_id,
                        candidate_type,coach_action,coach_id,decision_summary,outcome_intent,status,recorded_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["decision_id"], candidate_id, candidate["diagnosis_id"],
                     candidate["problem_id"], athlete_id, candidate["assessment_id"],
                     candidate["candidate_type"], latest[0], coach_actor_id,
                     record["decision_summary"], outcome_intent, "RECORDED", now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_DECISION_RECORD_RECORDED", record=record,
                   timestamp=now, why="Decision recorded only after explicit Coach review; no autonomous execution authorized.")
    else:
        candidate = _memory_candidate(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                      athlete_id=athlete_id, candidate_id=candidate_id)
        if candidate is None:
            return None
        diagnosis = _memory_diagnosis(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, diagnosis_id=candidate["diagnosis_id"],
        )
        if diagnosis is None:
            return None
        _revalidate_diagnosis_evidence_memory(diagnosis, athlete_id)
        reviews = sorted([x for x in _MEMORY_REVIEWS.values() if x["candidate_id"] == candidate_id],
                         key=lambda x: (x["reviewed_at"], x["review_id"]))
        if not reviews:
            raise CoachDecisionConflict("Coach confirmation or override is required before recording the decision")
        record = {
            "decision_id": str(uuid.uuid4()), "candidate_id": candidate_id,
            "diagnosis_id": candidate["diagnosis_id"], "problem_id": candidate["problem_id"],
            "athlete_id": athlete_id, "assessment_id": candidate["assessment_id"],
            "candidate_type": candidate["candidate_type"], "coach_action": reviews[-1]["action"],
            "coach_id": coach_actor_id,
            "decision_summary": str(decision_summary or "").strip() or candidate["title"],
            "outcome_intent": outcome_intent, "status": "RECORDED",
            "coach_final_authority": True, "execution_authorized": False,
            "recorded_at": now,
        }
        _MEMORY_DECISIONS[record["decision_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_DECISION_RECORD_RECORDED", record=record,
               timestamp=now, why="Decision recorded only after explicit Coach review; no autonomous execution authorized.")
    return record


def list_decision_records(*, tenant_id: str, coach_actor_id: str,
                          athlete_id: str, candidate_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _candidate_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, candidate_id=candidate_id) is None:
                    return None
                cur.execute(
                    """SELECT r.decision_id,r.candidate_id,r.diagnosis_id,r.problem_id,r.athlete_id,
                              r.assessment_id,r.candidate_type,r.coach_action,r.coach_id,
                              r.decision_summary,r.outcome_intent,r.status,r.recorded_at
                       FROM kaizo_decision_records r
                       JOIN kaizo_decision_candidates c ON c.candidate_id=r.candidate_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=c.athlete_id
                       WHERE r.candidate_id=%s AND c.athlete_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY r.recorded_at,r.decision_id""",
                    (candidate_id, athlete_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "decision_id": x[0], "candidate_id": x[1], "diagnosis_id": x[2],
            "problem_id": x[3], "athlete_id": x[4], "assessment_id": x[5],
            "candidate_type": x[6], "coach_action": x[7], "coach_id": x[8],
            "decision_summary": x[9], "outcome_intent": x[10], "status": x[11],
            "recorded_at": x[12], "coach_final_authority": True,
            "execution_authorized": False,
        } for x in rows]
    candidate = _memory_candidate(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, candidate_id=candidate_id)
    if candidate is None:
        return None
    return sorted([x for x in _MEMORY_DECISIONS.values() if x["candidate_id"] == candidate_id],
                  key=lambda x: (x["recorded_at"], x["decision_id"]))
