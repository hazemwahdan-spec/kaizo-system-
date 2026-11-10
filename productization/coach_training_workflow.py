"""Protected Coach training plan, session and dosage proposal workflows.

FEAT-026–028. Training artefacts inherit scope from a Coach-recorded decision.
They remain DRAFT proposals: this module never schedules, starts, or executes
training.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import persistence
from . import coach_decision_workflow


_MEMORY_PLANS: dict[str, dict[str, Any]] = {}
_MEMORY_SESSIONS: dict[str, dict[str, Any]] = {}
_MEMORY_DOSAGES: dict[str, dict[str, Any]] = {}
_MEMORY_AUDIT: list[dict[str, Any]] = []


class CoachTrainingNotFound(LookupError):
    pass


class CoachTrainingConflict(RuntimeError):
    pass


def reset_memory_state() -> None:
    _MEMORY_PLANS.clear()
    _MEMORY_SESSIONS.clear()
    _MEMORY_DOSAGES.clear()
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


def _decision_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
                  athlete_id: str, decision_id: str, lock: bool = False):
    sql = """SELECT d.decision_id,d.candidate_id,d.diagnosis_id,d.problem_id,
                    d.athlete_id,d.assessment_id,d.candidate_type,d.coach_action,
                    d.coach_id,d.decision_summary,d.outcome_intent,d.status,d.recorded_at
             FROM kaizo_decision_records d
             JOIN kaizo_coach_decision_reviews r
               ON r.candidate_id=d.candidate_id AND r.coach_id=d.coach_id
                  AND r.action=d.coach_action
             JOIN kaizo_decision_candidates c
               ON c.candidate_id=d.candidate_id AND c.athlete_id=d.athlete_id
             JOIN kaizo_evidence_linked_diagnoses g
               ON g.diagnosis_id=d.diagnosis_id AND g.athlete_id=d.athlete_id
             JOIN kaizo_problem_statements p
               ON p.problem_id=d.problem_id AND p.athlete_id=d.athlete_id
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=d.athlete_id
             WHERE d.decision_id=%s AND d.athlete_id=%s AND d.coach_id=%s
               AND d.status='RECORDED' AND o.tenant_id=%s AND o.coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o,d"
    cur.execute(sql, (decision_id, athlete_id, coach_actor_id, tenant_id, coach_actor_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "decision_id": row[0], "candidate_id": row[1], "diagnosis_id": row[2],
        "problem_id": row[3], "athlete_id": row[4], "assessment_id": row[5],
        "candidate_type": row[6], "coach_action": row[7], "coach_id": row[8],
        "decision_summary": row[9], "outcome_intent": row[10], "status": row[11],
        "recorded_at": row[12], "coach_final_authority": True,
        "execution_authorized": False,
    }


def _memory_decision(*, tenant_id: str, coach_actor_id: str,
                     athlete_id: str, decision_id: str):
    decision = coach_decision_workflow._MEMORY_DECISIONS.get(decision_id)
    if (decision is None or decision.get("athlete_id") != athlete_id
            or decision.get("coach_id") != coach_actor_id
            or decision.get("status") != "RECORDED"):
        return None
    candidate = coach_decision_workflow._memory_candidate(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, candidate_id=decision["candidate_id"],
    )
    if candidate is None:
        return None
    return decision


def _plan_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
              athlete_id: str, plan_id: str, lock: bool = False):
    sql = """SELECT t.plan_id,t.athlete_id,t.decision_id,t.title,t.objective,
                    t.constraints,t.status,t.created_by,t.created_at
             FROM kaizo_training_plans t
             JOIN kaizo_decision_records d
               ON d.decision_id=t.decision_id AND d.athlete_id=t.athlete_id
             JOIN kaizo_coach_decision_reviews r
               ON r.candidate_id=d.candidate_id AND r.coach_id=d.coach_id
                  AND r.action=d.coach_action
             JOIN kaizo_decision_candidates c ON c.candidate_id=d.candidate_id
             JOIN kaizo_evidence_linked_diagnoses g ON g.diagnosis_id=d.diagnosis_id
             JOIN kaizo_problem_statements p ON p.problem_id=d.problem_id AND p.athlete_id=d.athlete_id
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=t.athlete_id
             WHERE t.plan_id=%s AND t.athlete_id=%s AND d.coach_id=%s
               AND d.status='RECORDED' AND o.tenant_id=%s AND o.coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o,t"
    cur.execute(sql, (plan_id, athlete_id, coach_actor_id, tenant_id, coach_actor_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "plan_id": row[0], "athlete_id": row[1], "decision_id": row[2],
        "title": row[3], "objective": row[4], "constraints": row[5],
        "status": row[6], "created_by": row[7], "created_at": row[8],
        "coach_final_authority": True, "execution_authorized": False,
    }


def _memory_plan(*, tenant_id: str, coach_actor_id: str,
                 athlete_id: str, plan_id: str):
    plan = _MEMORY_PLANS.get(plan_id)
    if plan is None or plan.get("athlete_id") != athlete_id:
        return None
    decision = _memory_decision(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, decision_id=plan["decision_id"],
    )
    return plan if decision is not None else None


def _session_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
                 athlete_id: str, session_id: str, lock: bool = False):
    sql = """SELECT s.session_id,s.plan_id,s.athlete_id,s.title,s.duration_minutes,
                    s.blocks,s.status,s.created_by,s.created_at
             FROM kaizo_training_sessions s
             JOIN kaizo_training_plans t ON t.plan_id=s.plan_id AND t.athlete_id=s.athlete_id
             JOIN kaizo_decision_records d ON d.decision_id=t.decision_id AND d.athlete_id=t.athlete_id
             JOIN kaizo_coach_decision_reviews r
               ON r.candidate_id=d.candidate_id AND r.coach_id=d.coach_id
                  AND r.action=d.coach_action
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=s.athlete_id
             WHERE s.session_id=%s AND s.athlete_id=%s AND d.coach_id=%s
               AND d.status='RECORDED' AND o.tenant_id=%s AND o.coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o,s,t"
    cur.execute(sql, (session_id, athlete_id, coach_actor_id, tenant_id, coach_actor_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "session_id": row[0], "plan_id": row[1], "athlete_id": row[2],
        "title": row[3], "duration_minutes": row[4], "blocks": row[5],
        "status": row[6], "created_by": row[7], "created_at": row[8],
        "coach_final_authority": True, "execution_authorized": False,
    }


def _memory_session(*, tenant_id: str, coach_actor_id: str,
                    athlete_id: str, session_id: str):
    session = _MEMORY_SESSIONS.get(session_id)
    if session is None or session.get("athlete_id") != athlete_id:
        return None
    plan = _memory_plan(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, plan_id=session["plan_id"],
    )
    return session if plan is not None else None


def create_training_plan(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, decision_id: str,
    title: str, objective: str, constraints: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    title, objective = str(title or "").strip(), str(objective or "").strip()
    if not title or not objective:
        raise ValueError("title and objective are required")
    if constraints is not None and not isinstance(constraints, dict):
        raise ValueError("constraints must be an object")
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                decision = _decision_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, decision_id=decision_id, lock=True,
                )
                if decision is None:
                    return None
                record = {
                    "plan_id": str(uuid.uuid4()), "athlete_id": athlete_id,
                    "decision_id": decision_id, "title": title, "objective": objective,
                    "constraints": constraints or {}, "status": "DRAFT",
                    "created_by": coach_actor_id, "created_at": now,
                    "coach_final_authority": True, "execution_authorized": False,
                }
                cur.execute(
                    """INSERT INTO kaizo_training_plans
                       (plan_id,athlete_id,decision_id,title,objective,constraints,status,created_by,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                    (record["plan_id"], athlete_id, decision_id, title, objective,
                     json.dumps(record["constraints"]), "DRAFT", coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_TRAINING_PLAN_CREATED", record=record,
                   timestamp=now, why="Draft plan created from a Coach-reviewed decision; no execution authorized.")
    else:
        decision = _memory_decision(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, decision_id=decision_id,
        )
        if decision is None:
            return None
        record = {
            "plan_id": str(uuid.uuid4()), "athlete_id": athlete_id,
            "decision_id": decision_id, "title": title, "objective": objective,
            "constraints": constraints or {}, "status": "DRAFT",
            "created_by": coach_actor_id, "created_at": now,
            "coach_final_authority": True, "execution_authorized": False,
        }
        _MEMORY_PLANS[record["plan_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_TRAINING_PLAN_CREATED", record=record,
               timestamp=now, why="Draft plan created from a Coach-reviewed decision; no execution authorized.")
    return record


def get_training_plan(*, tenant_id: str, coach_actor_id: str,
                      athlete_id: str, plan_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                return _plan_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                 athlete_id=athlete_id, plan_id=plan_id)
    return _memory_plan(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                        athlete_id=athlete_id, plan_id=plan_id)


def list_training_plans(*, tenant_id: str, coach_actor_id: str,
                        athlete_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT t.plan_id,t.athlete_id,t.decision_id,t.title,t.objective,
                              t.constraints,t.status,t.created_by,t.created_at
                       FROM kaizo_training_plans t
                       JOIN kaizo_decision_records d ON d.decision_id=t.decision_id AND d.athlete_id=t.athlete_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=t.athlete_id
                       WHERE t.athlete_id=%s AND d.coach_id=%s AND d.status='RECORDED'
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY t.created_at,t.plan_id""",
                    (athlete_id, coach_actor_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "plan_id": x[0], "athlete_id": x[1], "decision_id": x[2],
            "title": x[3], "objective": x[4], "constraints": x[5],
            "status": x[6], "created_by": x[7], "created_at": x[8],
            "coach_final_authority": True, "execution_authorized": False,
        } for x in rows]
    if not any(x.get("athlete_id") == athlete_id for x in _MEMORY_PLANS.values()):
        # Verify the requested athlete scope through any owned decision record.
        owned = any(
            d.get("athlete_id") == athlete_id and d.get("coach_id") == coach_actor_id
            for d in coach_decision_workflow._MEMORY_DECISIONS.values()
        )
        if not owned:
            return None
    return sorted(
        [x for x in _MEMORY_PLANS.values()
         if x.get("athlete_id") == athlete_id
         and _memory_decision(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                              athlete_id=athlete_id, decision_id=x["decision_id"]) is not None],
        key=lambda x: (x["created_at"], x["plan_id"]),
    )


def create_training_session(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, plan_id: str,
    title: str, duration_minutes: int, blocks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    title = str(title or "").strip()
    if not title or not isinstance(duration_minutes, int) or duration_minutes <= 0:
        raise ValueError("title and positive duration_minutes are required")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("at least one session block is required")
    names = []
    durations = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("each session block must be an object")
        name = str(block.get("name") or "").strip()
        minutes = block.get("duration_minutes")
        if not name or not isinstance(minutes, int) or minutes <= 0:
            raise ValueError("each block requires a name and positive duration_minutes")
        names.append(name)
        durations.append(minutes)
    if len(set(names)) != len(names):
        raise ValueError("session block names must be distinct")
    if sum(durations) != duration_minutes:
        raise ValueError("block durations must equal session duration")
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                plan = _plan_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, plan_id=plan_id, lock=True,
                )
                if plan is None:
                    return None
                record = {
                    "session_id": str(uuid.uuid4()), "plan_id": plan_id,
                    "athlete_id": athlete_id, "title": title,
                    "duration_minutes": duration_minutes, "blocks": blocks,
                    "status": "DRAFT", "created_by": coach_actor_id,
                    "created_at": now, "coach_final_authority": True,
                    "execution_authorized": False,
                }
                cur.execute(
                    """INSERT INTO kaizo_training_sessions
                       (session_id,plan_id,athlete_id,title,duration_minutes,blocks,status,created_by,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
                    (record["session_id"], plan_id, athlete_id, title, duration_minutes,
                     json.dumps(blocks), "DRAFT", coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_TRAINING_SESSION_CREATED", record=record,
                   timestamp=now, why="Draft session structure recorded under the owned plan; execution remains disabled.")
    else:
        plan = _memory_plan(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id, plan_id=plan_id)
        if plan is None:
            return None
        record = {
            "session_id": str(uuid.uuid4()), "plan_id": plan_id,
            "athlete_id": athlete_id, "title": title,
            "duration_minutes": duration_minutes, "blocks": blocks,
            "status": "DRAFT", "created_by": coach_actor_id,
            "created_at": now, "coach_final_authority": True,
            "execution_authorized": False,
        }
        _MEMORY_SESSIONS[record["session_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_TRAINING_SESSION_CREATED", record=record,
               timestamp=now, why="Draft session structure recorded under the owned plan; execution remains disabled.")
    return record


def get_training_session(*, tenant_id: str, coach_actor_id: str,
                          athlete_id: str, session_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                return _session_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                    athlete_id=athlete_id, session_id=session_id)
    return _memory_session(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                           athlete_id=athlete_id, session_id=session_id)


def list_training_sessions(*, tenant_id: str, coach_actor_id: str,
                           athlete_id: str, plan_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _plan_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                             athlete_id=athlete_id, plan_id=plan_id) is None:
                    return None
                cur.execute(
                    """SELECT s.session_id,s.plan_id,s.athlete_id,s.title,s.duration_minutes,
                              s.blocks,s.status,s.created_by,s.created_at
                       FROM kaizo_training_sessions s
                       JOIN kaizo_training_plans t ON t.plan_id=s.plan_id AND t.athlete_id=s.athlete_id
                       JOIN kaizo_decision_records d ON d.decision_id=t.decision_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=s.athlete_id
                       WHERE s.plan_id=%s AND s.athlete_id=%s AND d.coach_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY s.created_at,s.session_id""",
                    (plan_id, athlete_id, coach_actor_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "session_id": x[0], "plan_id": x[1], "athlete_id": x[2],
            "title": x[3], "duration_minutes": x[4], "blocks": x[5],
            "status": x[6], "created_by": x[7], "created_at": x[8],
            "coach_final_authority": True, "execution_authorized": False,
        } for x in rows]
    plan = _memory_plan(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                        athlete_id=athlete_id, plan_id=plan_id)
    if plan is None:
        return None
    return sorted([x for x in _MEMORY_SESSIONS.values() if x["plan_id"] == plan_id],
                  key=lambda x: (x["created_at"], x["session_id"]))


def create_training_dosage(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, session_id: str,
    block_name: str, sets: int, reps: int, rest_seconds: int = 0,
    dosage_notes: str | None = None,
) -> dict[str, Any] | None:
    block_name = str(block_name or "").strip()
    if not block_name:
        raise ValueError("block_name is required")
    if not isinstance(sets, int) or not isinstance(reps, int) or sets <= 0 or reps <= 0:
        raise ValueError("sets and reps must be positive integers")
    if not isinstance(rest_seconds, int) or rest_seconds < 0:
        raise ValueError("rest_seconds must be a non-negative integer")
    now = _now()
    if persistence.is_postgres_enabled():
        persistence._ensure_training_dosages_table()
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                session = _session_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, session_id=session_id, lock=True,
                )
                if session is None:
                    return None
                block_names = {str(x.get("name") or "").strip() for x in session.get("blocks") or []}
                if block_name not in block_names:
                    raise ValueError("block_name must match an existing session block")
                record = {
                    "dosage_id": str(uuid.uuid4()), "session_id": session_id,
                    "plan_id": session["plan_id"], "athlete_id": athlete_id,
                    "block_name": block_name, "sets": sets, "reps": reps,
                    "rest_seconds": rest_seconds,
                    "dosage_notes": str(dosage_notes or "").strip() or None,
                    "status": "DRAFT", "prescribed_by": coach_actor_id,
                    "created_at": now, "coach_final_authority": True,
                    "execution_authorized": False,
                }
                cur.execute(
                    """INSERT INTO kaizo_training_dosages
                       (dosage_id,session_id,plan_id,athlete_id,block_name,sets,reps,
                        rest_seconds,dosage_notes,status,prescribed_by,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["dosage_id"], session_id, session["plan_id"], athlete_id,
                     block_name, sets, reps, rest_seconds, record["dosage_notes"],
                     "DRAFT", coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_TRAINING_DOSAGE_PRESCRIBED", record=record,
                   timestamp=now, why="Draft dosage prescribed for an owned session; no execution authorized.")
    else:
        session = _memory_session(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                  athlete_id=athlete_id, session_id=session_id)
        if session is None:
            return None
        block_names = {str(x.get("name") or "").strip() for x in session.get("blocks") or []}
        if block_name not in block_names:
            raise ValueError("block_name must match an existing session block")
        record = {
            "dosage_id": str(uuid.uuid4()), "session_id": session_id,
            "plan_id": session["plan_id"], "athlete_id": athlete_id,
            "block_name": block_name, "sets": sets, "reps": reps,
            "rest_seconds": rest_seconds,
            "dosage_notes": str(dosage_notes or "").strip() or None,
            "status": "DRAFT", "prescribed_by": coach_actor_id,
            "created_at": now, "coach_final_authority": True,
            "execution_authorized": False,
        }
        _MEMORY_DOSAGES[record["dosage_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_TRAINING_DOSAGE_PRESCRIBED", record=record,
               timestamp=now, why="Draft dosage prescribed for an owned session; no execution authorized.")
    return record


def list_training_dosages(*, tenant_id: str, coach_actor_id: str,
                          athlete_id: str, session_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        persistence._ensure_training_dosages_table()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _session_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id, session_id=session_id) is None:
                    return None
                cur.execute(
                    """SELECT dosage_id,session_id,plan_id,athlete_id,block_name,sets,reps,
                              rest_seconds,dosage_notes,status,prescribed_by,created_at
                       FROM kaizo_training_dosages WHERE session_id=%s AND athlete_id=%s
                       ORDER BY created_at,dosage_id""",
                    (session_id, athlete_id),
                )
                rows = cur.fetchall()
        return [{
            "dosage_id": x[0], "session_id": x[1], "plan_id": x[2],
            "athlete_id": x[3], "block_name": x[4], "sets": x[5],
            "reps": x[6], "rest_seconds": x[7], "dosage_notes": x[8],
            "status": x[9], "prescribed_by": x[10], "created_at": x[11],
            "coach_final_authority": True, "execution_authorized": False,
        } for x in rows]
    session = _memory_session(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                              athlete_id=athlete_id, session_id=session_id)
    if session is None:
        return None
    return sorted([x for x in _MEMORY_DOSAGES.values() if x["session_id"] == session_id],
                  key=lambda x: (x["created_at"], x["dosage_id"]))


def get_training_dosage(*, tenant_id: str, coach_actor_id: str,
                        athlete_id: str, session_id: str, dosage_id: str) -> dict[str, Any] | None:
    if persistence.is_postgres_enabled():
        persistence._ensure_training_dosages_table()
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _session_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                athlete_id=athlete_id, session_id=session_id) is None:
                    return None
                cur.execute(
                    """SELECT d.dosage_id,d.session_id,d.plan_id,d.athlete_id,d.block_name,
                              d.sets,d.reps,d.rest_seconds,d.dosage_notes,d.status,
                              d.prescribed_by,d.created_at
                       FROM kaizo_training_dosages d
                       JOIN kaizo_training_sessions s ON s.session_id=d.session_id
                       JOIN kaizo_training_plans t ON t.plan_id=s.plan_id
                       JOIN kaizo_decision_records r ON r.decision_id=t.decision_id
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=d.athlete_id
                       WHERE d.dosage_id=%s AND d.session_id=%s AND d.athlete_id=%s
                         AND r.coach_id=%s AND o.tenant_id=%s AND o.coach_actor_id=%s""",
                    (dosage_id, session_id, athlete_id, coach_actor_id, tenant_id, coach_actor_id),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {
            "dosage_id": row[0], "session_id": row[1], "plan_id": row[2],
            "athlete_id": row[3], "block_name": row[4], "sets": row[5],
            "reps": row[6], "rest_seconds": row[7], "dosage_notes": row[8],
            "status": row[9], "prescribed_by": row[10], "created_at": row[11],
            "coach_final_authority": True, "execution_authorized": False,
        }
    session = _memory_session(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                              athlete_id=athlete_id, session_id=session_id)
    if session is None:
        return None
    dosage = _MEMORY_DOSAGES.get(dosage_id)
    if dosage is None or dosage.get("session_id") != session_id:
        return None
    return dosage
