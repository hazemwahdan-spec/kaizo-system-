"""FEAT-009 read-only, Coach-owned decision-cycle workspace assembly."""
from __future__ import annotations

from typing import Any

import persistence
from productization import coach_roster


_REQUIRED_TABLES = (
    "kaizo_assessments",
    "kaizo_assessment_evidence_attachments",
    "kaizo_evidence_records",
    "kaizo_state_snapshots",
    "kaizo_problem_statements",
    "kaizo_cause_context_framings",
    "kaizo_evidence_linked_diagnoses",
    "kaizo_decision_candidates",
    "kaizo_decision_rationales",
    "kaizo_decision_comparisons",
    "kaizo_coach_decision_reviews",
    "kaizo_decision_records",
    "kaizo_training_plans",
    "kaizo_training_sessions",
)
_OPTIONAL_TABLES = ("kaizo_training_workflow_records",)


def _rows(cur: Any, sql: str, params: tuple[Any, ...], columns: tuple[str, ...]) -> list[dict[str, Any]]:
    cur.execute(sql, params)
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _empty(status: str, message: str, *, available: bool = False) -> dict[str, Any]:
    return {
        "available": available,
        "status": status,
        "message": message,
        "assessments": [],
        "state_snapshots": [],
        "problem_statements": [],
        "cause_context_framings": [],
        "diagnoses": [],
        "decision_candidates": [],
        "decision_rationales": [],
        "decision_comparisons": [],
        "coach_reviews": [],
        "decisions": [],
        "training_plans": [],
        "training_sessions": [],
        "training_records": [],
        "source_tables": list(_REQUIRED_TABLES) + list(_OPTIONAL_TABLES),
        "missing_optional_tables": [],
        "read_only": True,
        "historical_backfill_performed": False,
        "coach_final_authority": True,
        "execution_authorized": False,
    }


def get_coach_decision_workspace(
    *, tenant_id: str, coach_actor_id: str, athlete_id: str
) -> dict[str, Any] | None:
    """Read all available decision-cycle records for one verified owned athlete.

    Every query independently joins the tenant/Coach ownership relation. The
    function never calls the unscoped Core assessment/evidence HTTP endpoints,
    never writes source data, and fails closed when durable storage is absent.
    """
    athlete = coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=coach_actor_id, athlete_id=athlete_id
    )
    if athlete is None:
        return None

    if not persistence.is_postgres_enabled():
        return _empty(
            "INSUFFICIENT_EVIDENCE",
            "Decision workspace requires durable PostgreSQL assessment, evidence, and workflow records.",
        )

    params = (tenant_id, coach_actor_id, athlete_id)
    result = _empty("INSUFFICIENT_EVIDENCE", "Required durable decision-cycle tables are unavailable.")
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT to_regclass('public.kaizo_assessments'),
                       to_regclass('public.kaizo_assessment_evidence_attachments'),
                       to_regclass('public.kaizo_evidence_records'),
                       to_regclass('public.kaizo_state_snapshots'),
                       to_regclass('public.kaizo_problem_statements'),
                       to_regclass('public.kaizo_cause_context_framings'),
                       to_regclass('public.kaizo_evidence_linked_diagnoses'),
                       to_regclass('public.kaizo_decision_candidates'),
                       to_regclass('public.kaizo_decision_rationales'),
                       to_regclass('public.kaizo_decision_comparisons'),
                       to_regclass('public.kaizo_coach_decision_reviews'),
                       to_regclass('public.kaizo_decision_records'),
                       to_regclass('public.kaizo_training_plans'),
                       to_regclass('public.kaizo_training_sessions'),
                       to_regclass('public.kaizo_training_workflow_records')
            """)
            tables = cur.fetchone()
            if not tables or any(table is None for table in tables[:-1]):
                return result
            workflow_table_available = tables[-1] is not None

            assessments: dict[str, dict[str, Any]] = {}
            cur.execute("""
                SELECT a.assessment_id, a.athlete_id, a.template_id, a.measurements,
                       a.recorded_by, a.assessed_at, a.created_at,
                       att.evidence_id, att.attached_by, att.attached_at,
                       e.evidence_level, e.status, e.source_ref, e.claim,
                       e.observed_value, e.verified_by, e.verified_at
                FROM kaizo_assessments a
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=a.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                LEFT JOIN kaizo_assessment_evidence_attachments att
                  ON att.assessment_id=a.assessment_id AND att.attached_by=%s
                LEFT JOIN kaizo_evidence_records e
                  ON e.evidence_id=att.evidence_id
                 AND e.subject_type='assessment'
                 AND e.subject_id=a.assessment_id
                WHERE a.athlete_id=%s AND a.recorded_by=%s
                ORDER BY a.assessed_at DESC, a.assessment_id, att.attached_at, att.evidence_id
            """, (tenant_id, coach_actor_id, coach_actor_id, athlete_id, coach_actor_id))
            for row in cur.fetchall():
                item = assessments.setdefault(row[0], {
                    "assessment_id": row[0], "athlete_id": row[1], "template_id": row[2],
                    "measurements": row[3], "recorded_by": row[4], "assessed_at": row[5],
                    "created_at": row[6], "evidence_attachments": [],
                })
                if row[7] is not None:
                    item["evidence_attachments"].append({
                        "evidence_id": row[7], "attached_by": row[8], "attached_at": row[9],
                        "evidence_record_found": row[10] is not None,
                        "evidence_level": row[10], "status": row[11],
                        "source_ref": row[12], "claim": row[13], "observed_value": row[14],
                        "verified_by": row[15], "verified_at": row[16],
                    })

            snapshots = _rows(cur, """
                SELECT s.snapshot_id,s.assessment_id,s.snapshot_type,s.measurements,s.kpis,
                       s.captured_by,s.captured_at,s.created_at
                FROM kaizo_state_snapshots s
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=s.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE s.athlete_id=%s AND s.captured_by=%s ORDER BY s.captured_at DESC,s.snapshot_id
            """, params + (coach_actor_id,), ("snapshot_id","assessment_id","snapshot_type","measurements","kpis",
                          "captured_by","captured_at","created_at"))

            problems = _rows(cur, """
                SELECT p.problem_id,p.assessment_id,p.statement,p.problem_type,p.impact,
                       p.context,p.structured_fields,p.status,p.created_by,p.created_at,p.updated_at
                FROM kaizo_problem_statements p
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=p.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE p.athlete_id=%s AND p.created_by=%s ORDER BY p.created_at,p.problem_id
            """, params + (coach_actor_id,), ("problem_id","assessment_id","statement","problem_type","impact",
                          "context","structured_fields","status","created_by","created_at","updated_at"))

            framings = _rows(cur, """
                SELECT f.framing_id,f.problem_id,f.assessment_id,f.cause,f.context,
                       f.contributing_factors,f.framed_by,f.framed_at
                FROM kaizo_cause_context_framings f
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=f.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE f.athlete_id=%s AND f.framed_by=%s ORDER BY f.framed_at,f.framing_id
            """, params + (coach_actor_id,), ("framing_id","problem_id","assessment_id","cause","context",
                          "contributing_factors","framed_by","framed_at"))

            diagnoses = _rows(cur, """
                SELECT d.diagnosis_id,d.problem_id,d.assessment_id,d.evidence_ids,d.diagnosis,
                       d.diagnosed_by,d.confidence,d.resolution_state,d.diagnosed_at
                FROM kaizo_evidence_linked_diagnoses d
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=d.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE d.athlete_id=%s AND d.diagnosed_by=%s ORDER BY d.diagnosed_at,d.diagnosis_id
            """, params + (coach_actor_id,), ("diagnosis_id","problem_id","assessment_id","evidence_ids","diagnosis",
                          "diagnosed_by","confidence","resolution_state","diagnosed_at"))

            candidates = _rows(cur, """
                SELECT c.candidate_id,c.diagnosis_id,c.problem_id,c.assessment_id,c.candidate_type,
                       c.title,c.rationale,c.source_diagnosis,c.status,c.generated_by,c.created_at
                FROM kaizo_decision_candidates c
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=c.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE c.athlete_id=%s AND c.generated_by=%s ORDER BY c.created_at,c.candidate_id
            """, params + (coach_actor_id,), ("candidate_id","diagnosis_id","problem_id","assessment_id","candidate_type",
                          "title","rationale","source_diagnosis","status","generated_by","created_at"))

            rationales = _rows(cur, """
                SELECT r.rationale_id,r.candidate_id,r.diagnosis_id,r.problem_id,r.assessment_id,
                       r.rationale,r.evidence_ids,r.recorded_by,r.recorded_at
                FROM kaizo_decision_rationales r
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=r.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE r.athlete_id=%s AND r.recorded_by=%s ORDER BY r.recorded_at,r.rationale_id
            """, params + (coach_actor_id,), ("rationale_id","candidate_id","diagnosis_id","problem_id","assessment_id",
                          "rationale","evidence_ids","recorded_by","recorded_at"))

            comparisons = _rows(cur, """
                SELECT c.comparison_id,c.diagnosis_id,c.candidate_ids,c.alternatives,
                       c.comparison_status,c.compared_by,c.compared_at
                FROM kaizo_decision_comparisons c
                JOIN kaizo_evidence_linked_diagnoses d ON d.diagnosis_id=c.diagnosis_id
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=d.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE d.athlete_id=%s AND c.compared_by=%s ORDER BY c.compared_at,c.comparison_id
            """, params + (coach_actor_id,), ("comparison_id","diagnosis_id","candidate_ids","alternatives",
                          "comparison_status","compared_by","compared_at"))

            reviews = _rows(cur, """
                SELECT r.review_id,r.candidate_id,r.diagnosis_id,r.problem_id,r.assessment_id,
                       r.action,r.status,r.coach_id,r.override_reason,r.reviewed_at
                FROM kaizo_coach_decision_reviews r
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=r.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE r.athlete_id=%s AND r.coach_id=%s ORDER BY r.reviewed_at,r.review_id
            """, params + (coach_actor_id,), ("review_id","candidate_id","diagnosis_id","problem_id","assessment_id",
                          "action","status","coach_id","override_reason","reviewed_at"))

            decisions = _rows(cur, """
                SELECT d.decision_id,d.candidate_id,d.diagnosis_id,d.problem_id,d.assessment_id,
                       d.candidate_type,d.coach_action,d.coach_id,d.decision_summary,
                       d.outcome_intent,d.status,d.recorded_at
                FROM kaizo_decision_records d
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=d.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE d.athlete_id=%s AND d.coach_id=%s ORDER BY d.recorded_at,d.decision_id
            """, params + (coach_actor_id,), ("decision_id","candidate_id","diagnosis_id","problem_id","assessment_id",
                          "candidate_type","coach_action","coach_id","decision_summary",
                          "outcome_intent","status","recorded_at"))

            plans = _rows(cur, """
                SELECT p.plan_id,p.decision_id,p.title,p.objective,p.constraints,p.status,
                       p.created_by,p.created_at
                FROM kaizo_training_plans p
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=p.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE p.athlete_id=%s AND p.created_by=%s ORDER BY p.created_at,p.plan_id
            """, params + (coach_actor_id,), ("plan_id","decision_id","title","objective","constraints","status",
                          "created_by","created_at"))

            sessions = _rows(cur, """
                SELECT s.session_id,s.plan_id,s.title,s.duration_minutes,s.blocks,s.status,
                       s.created_by,s.created_at
                FROM kaizo_training_sessions s
                JOIN kaizo_coach_athlete_ownership owned
                  ON owned.athlete_id=s.athlete_id
                 AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                WHERE s.athlete_id=%s AND s.created_by=%s ORDER BY s.created_at,s.session_id
            """, params + (coach_actor_id,), ("session_id","plan_id","title","duration_minutes","blocks","status",
                          "created_by","created_at"))

            workflow = []
            if workflow_table_available:
                workflow = _rows(cur, """
                    SELECT w.record_id,w.feature_id,w.decision_id,w.session_id,w.payload,
                           w.created_by,w.created_at,w.coach_final_authority,w.execution_authorized
                    FROM kaizo_training_workflow_records w
                    JOIN kaizo_coach_athlete_ownership owned
                      ON owned.athlete_id=w.athlete_id
                     AND owned.tenant_id=%s AND owned.coach_actor_id=%s
                    WHERE w.athlete_id=%s AND w.created_by=%s ORDER BY w.created_at,w.record_id
                """, params + (coach_actor_id,), ("record_id","feature_id","decision_id","session_id","payload",
                              "created_by","created_at","coach_final_authority","execution_authorized"))

    data = {
        "assessments": list(assessments.values()),
        "state_snapshots": snapshots,
        "problem_statements": problems,
        "cause_context_framings": framings,
        "diagnoses": diagnoses,
        "decision_candidates": candidates,
        "decision_rationales": rationales,
        "decision_comparisons": comparisons,
        "coach_reviews": reviews,
        "decisions": decisions,
        "training_plans": plans,
        "training_sessions": sessions,
        "training_records": workflow,
    }
    has_records = any(bool(value) for value in data.values())
    return {
        **data,
        "available": True,
        "status": "WORKSPACE_AVAILABLE" if has_records else "NO_RECORDED_CYCLE",
        "message": None if has_records else "No persisted decision-cycle records exist for this athlete.",
        "source_tables": list(_REQUIRED_TABLES) + list(_OPTIONAL_TABLES),
        "missing_optional_tables": [] if workflow_table_available else list(_OPTIONAL_TABLES),
        "read_only": True,
        "historical_backfill_performed": False,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
