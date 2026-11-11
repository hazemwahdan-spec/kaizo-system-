"""Protected Coach progression, session-constraint, drill-library and problem/drill workflows.

FEAT-029–032. These are scoped advisory records. Approval is explicit,
evidence is revalidated, and no rule or drill authorizes autonomous execution.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

import persistence
from progression_rules import ProgressionRegressionRule, validate_rule
from session_constraints_notes import SessionConstraintNote, serialize_item
from drill_library import Drill, serialize_drill, validate_drill
from problem_drill_linkage import ProblemDrillLink, serialize_link, validate_link
from . import (
    coach_decision_workflow,
    coach_diagnostic_workflow,
    coach_training_workflow,
)


_MEMORY_RULES: dict[str, dict[str, Any]] = {}
_MEMORY_EVALUATIONS: dict[str, dict[str, Any]] = {}
_MEMORY_CONSTRAINTS: dict[str, dict[str, Any]] = {}
_MEMORY_DRILLS: dict[str, dict[str, Any]] = {}
_MEMORY_LINKS: dict[str, dict[str, Any]] = {}
_MEMORY_AUDIT: list[dict[str, Any]] = []


class CoachProgressionNotFound(LookupError):
    pass


class CoachProgressionConflict(RuntimeError):
    pass


def reset_memory_state() -> None:
    for store in (_MEMORY_RULES, _MEMORY_EVALUATIONS, _MEMORY_CONSTRAINTS,
                  _MEMORY_DRILLS, _MEMORY_LINKS):
        store.clear()
    _MEMORY_AUDIT.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit(*, tenant_id: str, coach_actor_id: str, action: str,
           record: dict[str, Any], timestamp: str, why: str) -> None:
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


def _validate_evidence_sql(cur: Any, evidence_ids: list[str], *, athlete_id: str,
                           problem_id: str, assessment_id: str) -> None:
    if not evidence_ids:
        raise ValueError("at least one evidence ID is required")
    for evidence_id in evidence_ids:
        try:
            coach_decision_workflow._evidence_sql(
                cur, evidence_id=evidence_id, athlete_id=athlete_id,
                problem_id=problem_id, assessment_id=assessment_id,
            )
        except coach_decision_workflow.CoachDecisionNotFound as exc:
            raise CoachProgressionNotFound(str(exc)) from exc
        except coach_decision_workflow.CoachDecisionConflict as exc:
            raise CoachProgressionConflict(str(exc)) from exc


def _validate_evidence_memory(evidence_ids: list[str], *, athlete_id: str,
                              problem_id: str, assessment_id: str) -> None:
    if not evidence_ids:
        raise ValueError("at least one evidence ID is required")
    for evidence_id in evidence_ids:
        try:
            coach_decision_workflow._evidence_memory(
                evidence_id=evidence_id, athlete_id=athlete_id,
                problem_id=problem_id, assessment_id=assessment_id,
            )
        except coach_decision_workflow.CoachDecisionNotFound as exc:
            raise CoachProgressionNotFound(str(exc)) from exc
        except coach_decision_workflow.CoachDecisionConflict as exc:
            raise CoachProgressionConflict(str(exc)) from exc


def _plan_context_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
                      athlete_id: str, plan_id: str, lock: bool = False):
    plan = coach_training_workflow._plan_sql(
        cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, plan_id=plan_id, lock=lock,
    )
    if plan is None:
        return None
    decision = coach_training_workflow._decision_sql(
        cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, decision_id=plan["decision_id"], lock=lock,
    )
    if decision is None:
        return None
    return plan, decision


def _plan_context_memory(*, tenant_id: str, coach_actor_id: str,
                         athlete_id: str, plan_id: str):
    plan = coach_training_workflow._memory_plan(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, plan_id=plan_id,
    )
    if plan is None:
        return None
    decision = coach_training_workflow._memory_decision(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, decision_id=plan["decision_id"],
    )
    if decision is None:
        return None
    return plan, decision


def _rule_from_row(row) -> dict[str, Any]:
    return {
        "rule_id": row[0], "tenant_id": row[1], "coach_actor_id": row[2],
        "plan_id": row[3], "athlete_id": row[4], "assessment_id": row[5],
        "metric": row[6], "operator": row[7], "threshold": row[8],
        "action": row[9], "adjustment": row[10], "rule_version": row[11],
        "approval_status": row[12], "evidence_ids": row[13],
        "created_by": row[14], "approved_by": row[15], "approved_at": row[16],
        "created_at": row[17], "updated_at": row[18], "name": row[19],
        "coach_final_authority": True, "execution_authorized": False,
    }


def _rule_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
              athlete_id: str, rule_id: str, lock: bool = False):
    sql = """SELECT r.rule_id,r.tenant_id,r.coach_actor_id,r.plan_id,r.athlete_id,
                    r.assessment_id,r.metric,r.operator,r.threshold,r.action,r.adjustment,
                    r.rule_version,r.approval_status,r.evidence_ids,r.created_by,
                    r.approved_by,r.approved_at,r.created_at,r.updated_at,r.name
             FROM kaizo_coach_progression_rules r
             JOIN kaizo_training_plans t ON t.plan_id=r.plan_id AND t.athlete_id=r.athlete_id
             JOIN kaizo_decision_records d ON d.decision_id=t.decision_id AND d.athlete_id=t.athlete_id
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=r.athlete_id
             WHERE r.rule_id=%s AND r.athlete_id=%s AND r.tenant_id=%s
               AND r.coach_actor_id=%s AND d.coach_id=%s
               AND o.tenant_id=%s AND o.coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o,r,t"
    cur.execute(sql, (rule_id, athlete_id, tenant_id, coach_actor_id,
                      coach_actor_id, tenant_id, coach_actor_id))
    row = cur.fetchone()
    return _rule_from_row(row) if row else None


def _memory_rule(*, tenant_id: str, coach_actor_id: str,
                 athlete_id: str, rule_id: str):
    rule = _MEMORY_RULES.get(rule_id)
    if rule is None or rule.get("tenant_id") != tenant_id or rule.get("coach_actor_id") != coach_actor_id or rule.get("athlete_id") != athlete_id:
        return None
    if _plan_context_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id, plan_id=rule["plan_id"]) is None:
        return None
    return rule


def _domain_rule(record: dict[str, Any]) -> ProgressionRegressionRule:
    return ProgressionRegressionRule(
        rule_id=record["rule_id"], name=record["name"], metric=record["metric"],
        operator=record["operator"], threshold=float(record["threshold"]),
        action=record["action"], adjustment=float(record["adjustment"]),
        created_by=record["created_by"], rule_version=record["rule_version"],
        approval_status=record["approval_status"], coach_final_authority=True,
        execution_authorized=False,
    )


def create_progression_rule(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str, plan_id: str,
    name: str, metric: str, operator: str, threshold: float, action: str,
    adjustment: float, rule_version: str, evidence_ids: list[str],
) -> dict[str, Any] | None:
    now = _now()
    rule_id = str(uuid.uuid4())
    if not math.isfinite(float(threshold)) or not math.isfinite(float(adjustment)):
        raise ValueError("threshold and adjustment must be finite numbers")
    values = {
        "rule_id": rule_id, "name": str(name or "").strip(),
        "metric": str(metric or "").strip(), "operator": str(operator or "").upper(),
        "threshold": float(threshold), "action": str(action or "").upper(),
        "adjustment": float(adjustment), "created_by": coach_actor_id,
        "rule_version": str(rule_version or "").strip(),
        "approval_status": "APPROVED", "coach_final_authority": True,
        "execution_authorized": False,
    }
    # Validate all semantic fields using the canonical domain validator, but persist DRAFT.
    validate_rule(_domain_rule(values))
    evidence_ids = list(dict.fromkeys(str(x).strip() for x in (evidence_ids or []) if str(x).strip()))
    if not evidence_ids:
        raise ValueError("at least one evidence ID is required")
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                context = _plan_context_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, plan_id=plan_id, lock=True,
                )
                if context is None:
                    return None
                plan, decision = context
                _validate_evidence_sql(cur, evidence_ids, athlete_id=athlete_id,
                                       problem_id=decision["problem_id"],
                                       assessment_id=decision["assessment_id"])
                record = {
                    **values, "tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
                    "plan_id": plan_id, "athlete_id": athlete_id,
                    "assessment_id": decision["assessment_id"],
                    "approval_status": "DRAFT", "evidence_ids": evidence_ids,
                    "approved_by": None, "approved_at": None,
                    "created_at": now, "updated_at": now,
                    "coach_final_authority": True, "execution_authorized": False,
                }
                cur.execute(
                    """INSERT INTO kaizo_coach_progression_rules
                       (rule_id,tenant_id,coach_actor_id,plan_id,athlete_id,assessment_id,
                        metric,operator,threshold,action,adjustment,rule_version,approval_status,
                        evidence_ids,created_by,approved_by,approved_at,created_at,updated_at,name)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s)""",
                    (rule_id, tenant_id, coach_actor_id, plan_id, athlete_id,
                     decision["assessment_id"], values["metric"], values["operator"],
                     values["threshold"], values["action"], values["adjustment"],
                     values["rule_version"], "DRAFT", json.dumps(evidence_ids),
                     coach_actor_id, None, None, now, now, values["name"]),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_PROGRESSION_RULE_CREATED", record=record,
                   timestamp=now, why="Evidence-linked progression rule created as DRAFT; explicit Coach approval is required.")
    else:
        context = _plan_context_memory(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, plan_id=plan_id,
        )
        if context is None:
            return None
        plan, decision = context
        _validate_evidence_memory(evidence_ids, athlete_id=athlete_id,
                                  problem_id=decision["problem_id"],
                                  assessment_id=decision["assessment_id"])
        record = {
            **values, "tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
            "plan_id": plan_id, "athlete_id": athlete_id,
            "assessment_id": decision["assessment_id"],
            "approval_status": "DRAFT", "evidence_ids": evidence_ids,
            "approved_by": None, "approved_at": None,
            "created_at": now, "updated_at": now,
            "coach_final_authority": True, "execution_authorized": False,
        }
        _MEMORY_RULES[rule_id] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_PROGRESSION_RULE_CREATED", record=record,
               timestamp=now, why="Evidence-linked progression rule created as DRAFT; explicit Coach approval is required.")
    return record


def list_progression_rules(*, tenant_id: str, coach_actor_id: str,
                           athlete_id: str, plan_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _plan_context_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                     athlete_id=athlete_id, plan_id=plan_id) is None:
                    return None
                cur.execute(
                    """SELECT r.rule_id,r.tenant_id,r.coach_actor_id,r.plan_id,r.athlete_id,
                              r.assessment_id,r.metric,r.operator,r.threshold,r.action,r.adjustment,
                              r.rule_version,r.approval_status,r.evidence_ids,r.created_by,
                              r.approved_by,r.approved_at,r.created_at,r.updated_at,r.name
                       FROM kaizo_coach_progression_rules r
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=r.athlete_id
                       WHERE r.plan_id=%s AND r.athlete_id=%s AND r.tenant_id=%s
                         AND r.coach_actor_id=%s AND o.tenant_id=%s AND o.coach_actor_id=%s
                       ORDER BY r.created_at,r.rule_id""",
                    (plan_id, athlete_id, tenant_id, coach_actor_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [_rule_from_row(x) for x in rows]
    if _plan_context_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id, plan_id=plan_id) is None:
        return None
    return sorted([x for x in _MEMORY_RULES.values() if x["plan_id"] == plan_id
                   and x["athlete_id"] == athlete_id and x["tenant_id"] == tenant_id
                   and x["coach_actor_id"] == coach_actor_id],
                  key=lambda x: (x["created_at"], x["rule_id"]))


def approve_progression_rule(*, tenant_id: str, coach_actor_id: str,
                             athlete_id: str, rule_id: str) -> dict[str, Any] | None:
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                rule = _rule_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                 athlete_id=athlete_id, rule_id=rule_id, lock=True)
                if rule is None:
                    return None
                if rule["approval_status"] == "RETIRED":
                    raise CoachProgressionConflict("retired rules cannot be approved")
                decision = _plan_context_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, plan_id=rule["plan_id"], lock=True,
                )[1]
                _validate_evidence_sql(cur, rule["evidence_ids"], athlete_id=athlete_id,
                                       problem_id=decision["problem_id"],
                                       assessment_id=rule["assessment_id"])
                candidate = {**rule, "approval_status": "APPROVED"}
                validate_rule(_domain_rule(candidate))
                cur.execute(
                    """UPDATE kaizo_coach_progression_rules
                       SET approval_status='APPROVED',approved_by=%s,approved_at=%s,updated_at=%s
                       WHERE rule_id=%s""",
                    (coach_actor_id, now, now, rule_id),
                )
                rule.update({"approval_status": "APPROVED", "approved_by": coach_actor_id,
                             "approved_at": now, "updated_at": now})
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_PROGRESSION_RULE_APPROVED", record=rule,
                   timestamp=now, why="Authenticated Coach explicitly approved a versioned evidence-backed progression rule.")
    else:
        rule = _memory_rule(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id, rule_id=rule_id)
        if rule is None:
            return None
        if rule["approval_status"] == "RETIRED":
            raise CoachProgressionConflict("retired rules cannot be approved")
        context = _plan_context_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                       athlete_id=athlete_id, plan_id=rule["plan_id"])
        _validate_evidence_memory(rule["evidence_ids"], athlete_id=athlete_id,
                                  problem_id=context[1]["problem_id"],
                                  assessment_id=rule["assessment_id"])
        candidate = {**rule, "approval_status": "APPROVED"}
        validate_rule(_domain_rule(candidate))
        rule.update({"approval_status": "APPROVED", "approved_by": coach_actor_id,
                     "approved_at": now, "updated_at": now})
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_PROGRESSION_RULE_APPROVED", record=rule,
               timestamp=now, why="Authenticated Coach explicitly approved a versioned evidence-backed progression rule.")
    return rule


def evaluate_progression_rule(*, tenant_id: str, coach_actor_id: str,
                              athlete_id: str, rule_id: str,
                              observed_value: float) -> dict[str, Any] | None:
    if not math.isfinite(float(observed_value)):
        raise ValueError("observed_value must be a finite number")
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                rule = _rule_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                 athlete_id=athlete_id, rule_id=rule_id, lock=True)
                if rule is None:
                    return None
                if rule["approval_status"] != "APPROVED":
                    raise CoachProgressionConflict("only APPROVED rules may be evaluated")
                context = _plan_context_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, plan_id=rule["plan_id"], lock=True,
                )
                if context is None:
                    return None
                _validate_evidence_sql(cur, rule["evidence_ids"], athlete_id=athlete_id,
                                       problem_id=context[1]["problem_id"],
                                       assessment_id=rule["assessment_id"])
                domain = _domain_rule(rule)
                result = domain.evaluate(float(observed_value))
                record = {
                    "evaluation_id": str(uuid.uuid4()), "rule_id": rule_id,
                    "tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
                    "athlete_id": athlete_id, "observed_value": float(observed_value),
                    "matched": result["matched"], "recommended_action": result["action"],
                    "adjustment": result["adjustment"], "evaluated_by": coach_actor_id,
                    "evaluated_at": now, "coach_final_authority": True,
                    "execution_authorized": False,
                }
                cur.execute(
                    """INSERT INTO kaizo_coach_progression_evaluations
                       (evaluation_id,rule_id,tenant_id,coach_actor_id,athlete_id,observed_value,
                        matched,recommended_action,adjustment,evaluated_by,evaluated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["evaluation_id"], rule_id, tenant_id, coach_actor_id,
                     athlete_id, float(observed_value), result["matched"], result["action"],
                     result["adjustment"], coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_PROGRESSION_RULE_EVALUATED", record=record,
                   timestamp=now, why="Approved progression rule evaluated as advisory output; no training action executed.")
    else:
        rule = _memory_rule(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                            athlete_id=athlete_id, rule_id=rule_id)
        if rule is None:
            return None
        if rule["approval_status"] != "APPROVED":
            raise CoachProgressionConflict("only APPROVED rules may be evaluated")
        context = _plan_context_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                       athlete_id=athlete_id, plan_id=rule["plan_id"])
        _validate_evidence_memory(rule["evidence_ids"], athlete_id=athlete_id,
                                  problem_id=context[1]["problem_id"],
                                  assessment_id=rule["assessment_id"])
        result = _domain_rule({**rule, "name": rule["metric"]}).evaluate(float(observed_value))
        record = {
            "evaluation_id": str(uuid.uuid4()), "rule_id": rule_id,
            "tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
            "athlete_id": athlete_id, "observed_value": float(observed_value),
            "matched": result["matched"], "recommended_action": result["action"],
            "adjustment": result["adjustment"], "evaluated_by": coach_actor_id,
            "evaluated_at": now, "coach_final_authority": True,
            "execution_authorized": False,
        }
        _MEMORY_EVALUATIONS[record["evaluation_id"]] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_PROGRESSION_RULE_EVALUATED", record=record,
               timestamp=now, why="Approved progression rule evaluated as advisory output; no training action executed.")
    return record


def list_progression_evaluations(*, tenant_id: str, coach_actor_id: str,
                                 athlete_id: str, rule_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                rule = _rule_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                 athlete_id=athlete_id, rule_id=rule_id)
                if rule is None:
                    return None
                cur.execute(
                    """SELECT evaluation_id,rule_id,tenant_id,coach_actor_id,athlete_id,
                              observed_value,matched,recommended_action,adjustment,evaluated_by,evaluated_at
                       FROM kaizo_coach_progression_evaluations
                       WHERE rule_id=%s AND tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                       ORDER BY evaluated_at,evaluation_id""",
                    (rule_id, tenant_id, coach_actor_id, athlete_id),
                )
                rows = cur.fetchall()
        return [{
            "evaluation_id": x[0], "rule_id": x[1], "tenant_id": x[2],
            "coach_actor_id": x[3], "athlete_id": x[4], "observed_value": x[5],
            "matched": x[6], "recommended_action": x[7], "adjustment": x[8],
            "evaluated_by": x[9], "evaluated_at": x[10],
            "coach_final_authority": True, "execution_authorized": False,
        } for x in rows]
    if _memory_rule(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, rule_id=rule_id) is None:
        return None
    return sorted([x for x in _MEMORY_EVALUATIONS.values() if x["rule_id"] == rule_id
                   and x["tenant_id"] == tenant_id and x["coach_actor_id"] == coach_actor_id
                   and x["athlete_id"] == athlete_id],
                  key=lambda x: (x["evaluated_at"], x["evaluation_id"]))


def _session_context_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
                         athlete_id: str, session_id: str, lock: bool = False):
    session = coach_training_workflow._session_sql(
        cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, session_id=session_id, lock=lock,
    )
    if session is None:
        return None
    return session


def _session_context_memory(*, tenant_id: str, coach_actor_id: str,
                            athlete_id: str, session_id: str):
    return coach_training_workflow._memory_session(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, session_id=session_id,
    )


def create_session_constraint(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
    session_id: str, kind: str, content: str, priority: str = "NORMAL",
) -> dict[str, Any] | None:
    now = _now()
    item = SessionConstraintNote(
        item_id=str(uuid.uuid4()), session_id=session_id,
        kind=str(kind or "").upper(), content=str(content or ""),
        priority=str(priority or "").upper(), created_by=coach_actor_id,
    )
    record = serialize_item(item)
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                session = _session_context_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, session_id=session_id, lock=True,
                )
                if session is None:
                    return None
                record.update({"tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
                               "athlete_id": athlete_id, "plan_id": session["plan_id"],
                               "created_at": now})
                cur.execute(
                    """INSERT INTO kaizo_coach_session_constraints
                       (constraint_id,tenant_id,coach_actor_id,session_id,plan_id,athlete_id,
                        kind,content,priority,created_by,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (record["item_id"], tenant_id, coach_actor_id, session_id,
                     session["plan_id"], athlete_id, item.kind, item.content.strip(),
                     item.priority, coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_SESSION_CONSTRAINT_NOTE_CREATED", record=record,
                   timestamp=now, why="Session constraint/note attached to an owned draft session.")
    else:
        session = _session_context_memory(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, session_id=session_id,
        )
        if session is None:
            return None
        record.update({"tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
                       "athlete_id": athlete_id, "plan_id": session["plan_id"],
                       "created_at": now})
        _MEMORY_CONSTRAINTS[item.item_id] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_SESSION_CONSTRAINT_NOTE_CREATED", record=record,
               timestamp=now, why="Session constraint/note attached to an owned draft session.")
    return record


def list_session_constraints(*, tenant_id: str, coach_actor_id: str,
                              athlete_id: str, session_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _session_context_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                        athlete_id=athlete_id, session_id=session_id) is None:
                    return None
                cur.execute(
                    """SELECT constraint_id,tenant_id,coach_actor_id,athlete_id,plan_id,
                              session_id,kind,content,priority,created_by,created_at
                       FROM kaizo_coach_session_constraints
                       WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s AND session_id=%s
                       ORDER BY created_at,constraint_id""",
                    (tenant_id, coach_actor_id, athlete_id, session_id),
                )
                rows = cur.fetchall()
        return [{
            "item_id": x[0], "tenant_id": x[1], "coach_actor_id": x[2],
            "athlete_id": x[3], "plan_id": x[4], "session_id": x[5],
            "kind": x[6], "content": x[7], "priority": x[8],
            "created_by": x[9], "created_at": x[10],
            "coach_final_authority": True, "execution_authorized": False,
        } for x in rows]
    if _session_context_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                               athlete_id=athlete_id, session_id=session_id) is None:
        return None
    return sorted([x for x in _MEMORY_CONSTRAINTS.values() if x["session_id"] == session_id
                   and x["tenant_id"] == tenant_id and x["coach_actor_id"] == coach_actor_id
                   and x["athlete_id"] == athlete_id],
                  key=lambda x: (x["created_at"], x["item_id"]))


def _drill_from_payload(payload: dict[str, Any]) -> Drill:
    values = dict(payload)
    for key in ("coach_cues", "common_errors", "evidence", "source"):
        values[key] = tuple(values.get(key) or ())
    return Drill(**values)


def _drill_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
               drill_id: str, lock: bool = False):
    sql = """SELECT drill_id,tenant_id,coach_actor_id,source_assessment_id,payload,
                    status,coach_review,created_by,approved_by,approved_at,created_at,updated_at
             FROM kaizo_coach_drill_library
             WHERE drill_id=%s AND tenant_id=%s AND coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE"
    cur.execute(sql, (drill_id, tenant_id, coach_actor_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {
        "drill_id": row[0], "tenant_id": row[1], "coach_actor_id": row[2],
        "source_assessment_id": row[3], "payload": row[4], "status": row[5],
        "coach_review": row[6], "created_by": row[7], "approved_by": row[8],
        "approved_at": row[9], "created_at": row[10], "updated_at": row[11],
    }


def _memory_drill(*, tenant_id: str, coach_actor_id: str, drill_id: str):
    drill = _MEMORY_DRILLS.get(drill_id)
    if drill is None or drill["tenant_id"] != tenant_id or drill["coach_actor_id"] != coach_actor_id:
        return None
    return drill


def create_drill(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
    assessment_id: str, drill_fields: dict[str, Any], evidence_ids: list[str],
    source_refs: list[str],
) -> dict[str, Any] | None:
    now = _now()
    drill_id = str(uuid.uuid4())
    evidence_ids = list(dict.fromkeys(str(x).strip() for x in (evidence_ids or []) if str(x).strip()))
    source_refs = list(dict.fromkeys(str(x).strip() for x in (source_refs or []) if str(x).strip()))
    payload = {
        "drill_id": drill_id, **drill_fields,
        "evidence": tuple(evidence_ids), "source": tuple(source_refs),
        "coach_review": False, "coach_final_authority": True,
        "execution_authorized": False,
    }
    drill = _drill_from_payload(payload)
    validate_drill(drill)
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                # Assessment ownership is the authority for the source evidence and authored drill.
                cur.execute(
                    """SELECT a.assessment_id FROM kaizo_assessments a
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
                       WHERE a.assessment_id=%s AND a.athlete_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       FOR UPDATE OF a,o""",
                    (assessment_id, athlete_id, tenant_id, coach_actor_id),
                )
                if cur.fetchone() is None:
                    return None
                _validate_evidence_sql(cur, evidence_ids, athlete_id=athlete_id,
                                       problem_id="", assessment_id=assessment_id)
                record = {
                    "drill_id": drill_id, "tenant_id": tenant_id,
                    "coach_actor_id": coach_actor_id, "source_assessment_id": assessment_id,
                    "payload": serialize_drill(drill), "status": "DRAFT",
                    "coach_review": False, "created_by": coach_actor_id,
                    "approved_by": None, "approved_at": None,
                    "created_at": now, "updated_at": now,
                    "coach_final_authority": True, "execution_authorized": False,
                }
                cur.execute(
                    """INSERT INTO kaizo_coach_drill_library
                       (drill_id,tenant_id,coach_actor_id,source_assessment_id,payload,status,
                        coach_review,created_by,approved_by,approved_at,created_at,updated_at)
                       VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)""",
                    (drill_id, tenant_id, coach_actor_id, assessment_id,
                     json.dumps(record["payload"]), "DRAFT", False, coach_actor_id,
                     None, None, now, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_DRILL_CREATED", record=record,
                   timestamp=now, why="Coach-authored evidence-aware drill created as DRAFT; publication requires explicit Coach review.")
    else:
        from . import coach_assessment_workflow
        if coach_assessment_workflow.get_assessment(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, assessment_id=assessment_id,
        ) is None:
            return None
        _validate_evidence_memory(evidence_ids, athlete_id=athlete_id,
                                  problem_id="", assessment_id=assessment_id)
        record = {
            "drill_id": drill_id, "tenant_id": tenant_id,
            "coach_actor_id": coach_actor_id, "source_assessment_id": assessment_id,
            "payload": serialize_drill(drill), "status": "DRAFT",
            "coach_review": False, "created_by": coach_actor_id,
            "approved_by": None, "approved_at": None,
            "created_at": now, "updated_at": now,
            "coach_final_authority": True, "execution_authorized": False,
        }
        _MEMORY_DRILLS[drill_id] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_DRILL_CREATED", record=record,
               timestamp=now, why="Coach-authored evidence-aware drill created as DRAFT; publication requires explicit Coach review.")
    return record


def approve_drill(*, tenant_id: str, coach_actor_id: str,
                  athlete_id: str, drill_id: str) -> dict[str, Any] | None:
    now = _now()
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                drill = _drill_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                   drill_id=drill_id, lock=True)
                if drill is None:
                    return None
                cur.execute(
                    """SELECT a.assessment_id FROM kaizo_assessments a
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=a.athlete_id
                       WHERE a.assessment_id=%s AND a.athlete_id=%s
                         AND o.tenant_id=%s AND o.coach_actor_id=%s
                       FOR UPDATE OF a,o""",
                    (drill["source_assessment_id"], athlete_id, tenant_id, coach_actor_id),
                )
                if cur.fetchone() is None:
                    return None
                payload = dict(drill["payload"])
                _validate_evidence_sql(cur, payload.get("evidence", []),
                                       athlete_id=athlete_id, problem_id="",
                                       assessment_id=drill["source_assessment_id"])
                payload["coach_review"] = True
                validate_drill(_drill_from_payload(payload))
                cur.execute(
                    """UPDATE kaizo_coach_drill_library SET payload=%s::jsonb,status='PUBLISHED',
                       coach_review=TRUE,approved_by=%s,approved_at=%s,updated_at=%s WHERE drill_id=%s""",
                    (json.dumps(payload), coach_actor_id, now, now, drill_id),
                )
                drill.update({"payload": payload, "status": "PUBLISHED", "coach_review": True,
                              "approved_by": coach_actor_id, "approved_at": now, "updated_at": now})
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_DRILL_APPROVED", record=drill,
                   timestamp=now, why="Authenticated Coach reviewed and published the evidence-aware drill.")
    else:
        drill = _memory_drill(tenant_id=tenant_id, coach_actor_id=coach_actor_id, drill_id=drill_id)
        if drill is None:
            return None
        from . import coach_assessment_workflow
        if coach_assessment_workflow.get_assessment(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, assessment_id=drill["source_assessment_id"],
        ) is None:
            return None
        payload = dict(drill["payload"])
        _validate_evidence_memory(payload.get("evidence", []), athlete_id=athlete_id,
                                  problem_id="", assessment_id=drill["source_assessment_id"])
        payload["coach_review"] = True
        validate_drill(_drill_from_payload(payload))
        drill.update({"payload": payload, "status": "PUBLISHED", "coach_review": True,
                      "approved_by": coach_actor_id, "approved_at": now, "updated_at": now})
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_DRILL_APPROVED", record=drill,
               timestamp=now, why="Authenticated Coach reviewed and published the evidence-aware drill.")
    return drill


def list_drills(*, tenant_id: str, coach_actor_id: str,
                include_drafts: bool = False) -> list[dict[str, Any]]:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                status_filter = "" if include_drafts else "AND status='PUBLISHED' AND coach_review=TRUE"
                cur.execute(
                    f"""SELECT drill_id,tenant_id,coach_actor_id,source_assessment_id,payload,
                               status,coach_review,created_by,approved_by,approved_at,created_at,updated_at
                        FROM kaizo_coach_drill_library
                        WHERE tenant_id=%s AND coach_actor_id=%s {status_filter}
                        ORDER BY created_at,drill_id""",
                    (tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [{
            "drill_id": x[0], "tenant_id": x[1], "coach_actor_id": x[2],
            "source_assessment_id": x[3], "payload": x[4],
            "status": x[5], "coach_review": x[6], "created_by": x[7],
            "approved_by": x[8], "approved_at": x[9], "created_at": x[10],
            "updated_at": x[11], "coach_final_authority": True,
            "execution_authorized": False,
        } for x in rows]
    return sorted([
        x for x in _MEMORY_DRILLS.values()
        if x["tenant_id"] == tenant_id and x["coach_actor_id"] == coach_actor_id
        and (include_drafts or (x["status"] == "PUBLISHED" and x["coach_review"]))
    ], key=lambda x: (x["created_at"], x["drill_id"]))


def _problem_context_sql(cur: Any, *, tenant_id: str, coach_actor_id: str,
                         athlete_id: str, problem_id: str, lock: bool = False):
    sql = """SELECT p.problem_id,p.athlete_id,p.assessment_id,p.statement
             FROM kaizo_problem_statements p
             JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=p.athlete_id
             WHERE p.problem_id=%s AND p.athlete_id=%s
               AND o.tenant_id=%s AND o.coach_actor_id=%s"""
    if lock:
        sql += " FOR UPDATE OF o,p"
    cur.execute(sql, (problem_id, athlete_id, tenant_id, coach_actor_id))
    row = cur.fetchone()
    if row is None:
        return None
    return {"problem_id": row[0], "athlete_id": row[1],
            "assessment_id": row[2], "statement": row[3]}


def _problem_context_memory(*, tenant_id: str, coach_actor_id: str,
                            athlete_id: str, problem_id: str):
    return coach_diagnostic_workflow._memory_problem(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id,
        athlete_id=athlete_id, problem_id=problem_id,
    )


def _link_from_row(row) -> dict[str, Any]:
    return {
        "link_id": row[0], "tenant_id": row[1], "coach_actor_id": row[2],
        "problem_id": row[3], "drill_id": row[4], "athlete_id": row[5],
        "assessment_id": row[6], "rationale": row[7], "evidence_ids": row[8],
        "created_by": row[9], "created_at": row[10],
        "coach_final_authority": True, "execution_authorized": False,
    }


def create_problem_drill_link(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str,
    problem_id: str, drill_id: str, rationale: str, evidence_ids: list[str],
) -> dict[str, Any] | None:
    now = _now()
    rationale = str(rationale or "").strip()
    if not rationale:
        raise ValueError("rationale is required")
    evidence_ids = list(dict.fromkeys(str(x).strip() for x in (evidence_ids or []) if str(x).strip()))
    if not evidence_ids:
        raise ValueError("at least one evidence ID is required")
    if persistence.is_postgres_enabled():
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                problem = _problem_context_sql(
                    cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                    athlete_id=athlete_id, problem_id=problem_id, lock=True,
                )
                if problem is None:
                    return None
                drill = _drill_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                   drill_id=drill_id, lock=True)
                if drill is None:
                    raise CoachProgressionNotFound("drill not found in this Coach/tenant library")
                if drill["status"] != "PUBLISHED" or not drill["coach_review"]:
                    raise CoachProgressionConflict("only Coach-reviewed PUBLISHED drills may be linked")
                _validate_evidence_sql(cur, evidence_ids, athlete_id=athlete_id,
                                       problem_id=problem_id, assessment_id=problem["assessment_id"])
                link = ProblemDrillLink(
                    link_id=str(uuid.uuid4()), problem_id=problem_id, drill_id=drill_id,
                    rationale=rationale, created_by=coach_actor_id,
                )
                payload = serialize_link(link)
                record = {
                    **payload, "tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
                    "athlete_id": athlete_id, "assessment_id": problem["assessment_id"],
                    "evidence_ids": evidence_ids, "created_at": now,
                }
                cur.execute(
                    """INSERT INTO kaizo_coach_problem_drill_links
                       (link_id,tenant_id,coach_actor_id,problem_id,drill_id,athlete_id,
                        assessment_id,rationale,evidence_ids,created_by,created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                    (link.link_id, tenant_id, coach_actor_id, problem_id, drill_id,
                     athlete_id, problem["assessment_id"], rationale,
                     json.dumps(evidence_ids), coach_actor_id, now),
                )
            _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                   action="COACH_PROBLEM_DRILL_LINK_CREATED", record=record,
                   timestamp=now, why="Problem linked to a Coach-reviewed drill with same-scope verified evidence.")
    else:
        problem = _problem_context_memory(
            tenant_id=tenant_id, coach_actor_id=coach_actor_id,
            athlete_id=athlete_id, problem_id=problem_id,
        )
        if problem is None:
            return None
        drill = _memory_drill(tenant_id=tenant_id, coach_actor_id=coach_actor_id, drill_id=drill_id)
        if drill is None:
            raise CoachProgressionNotFound("drill not found in this Coach/tenant library")
        if drill["status"] != "PUBLISHED" or not drill["coach_review"]:
            raise CoachProgressionConflict("only Coach-reviewed PUBLISHED drills may be linked")
        _validate_evidence_memory(evidence_ids, athlete_id=athlete_id,
                                  problem_id=problem_id, assessment_id=problem["assessment_id"])
        link = ProblemDrillLink(
            link_id=str(uuid.uuid4()), problem_id=problem_id, drill_id=drill_id,
            rationale=rationale, created_by=coach_actor_id,
        )
        record = {
            **serialize_link(link), "tenant_id": tenant_id, "coach_actor_id": coach_actor_id,
            "athlete_id": athlete_id, "assessment_id": problem["assessment_id"],
            "evidence_ids": evidence_ids, "created_at": now,
        }
        _MEMORY_LINKS[link.link_id] = record
        _audit(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
               action="COACH_PROBLEM_DRILL_LINK_CREATED", record=record,
               timestamp=now, why="Problem linked to a Coach-reviewed drill with same-scope verified evidence.")
    return record


def list_problem_drill_links(*, tenant_id: str, coach_actor_id: str,
                             athlete_id: str, problem_id: str) -> list[dict[str, Any]] | None:
    if persistence.is_postgres_enabled():
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                if _problem_context_sql(cur, tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                                        athlete_id=athlete_id, problem_id=problem_id) is None:
                    return None
                cur.execute(
                    """SELECT l.link_id,l.tenant_id,l.coach_actor_id,l.problem_id,l.drill_id,
                              l.athlete_id,l.assessment_id,l.rationale,l.evidence_ids,l.created_by,l.created_at
                       FROM kaizo_coach_problem_drill_links l
                       JOIN kaizo_coach_athlete_ownership o ON o.athlete_id=l.athlete_id
                       WHERE l.problem_id=%s AND l.athlete_id=%s
                         AND l.tenant_id=%s AND l.coach_actor_id=%s
                       ORDER BY l.created_at,l.link_id""",
                    (problem_id, athlete_id, tenant_id, coach_actor_id),
                )
                rows = cur.fetchall()
        return [_link_from_row(x) for x in rows]
    if _problem_context_memory(tenant_id=tenant_id, coach_actor_id=coach_actor_id,
                               athlete_id=athlete_id, problem_id=problem_id) is None:
        return None
    return sorted([x for x in _MEMORY_LINKS.values() if x["problem_id"] == problem_id
                   and x["athlete_id"] == athlete_id and x["tenant_id"] == tenant_id
                   and x["coach_actor_id"] == coach_actor_id],
                  key=lambda x: (x["created_at"], x["link_id"]))
