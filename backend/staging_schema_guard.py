"""Read-only verification of the pre-provisioned KAIZO Staging schema."""
from __future__ import annotations

import persistence


CORE_SCHEMA_TABLES = (
    "kaizo_athletes",
    "kaizo_assessments",
    "kaizo_assessment_evidence_attachments",
    "kaizo_kpi_definitions",
    "kaizo_coach_kpi_definitions",
    "kaizo_kpi_captures",
    "kaizo_audit_logs",
    "kaizo_evidence_records",
    "kaizo_digital_twin_state",
    "kaizo_knowledge_repository",
    "kaizo_state_snapshots",
    "kaizo_problem_library_selections",
    "kaizo_evidence_linked_diagnoses",
    "kaizo_decision_candidates",
    "kaizo_decision_rationales",
    "kaizo_decision_comparisons",
    "kaizo_coach_decision_reviews",
    "kaizo_decision_records",
    "kaizo_training_plans",
    "kaizo_training_sessions",
    "kaizo_training_dosages",
    "kaizo_cause_context_framings",
    "kaizo_problem_statements",
    "kaizo_coach_product_action_traces",
    "kaizo_coach_athlete_ownership",
    "kaizo_coach_athlete_status_history",
    "kaizo_coach_training_groups",
    "kaizo_coach_training_group_members",
    "kaizo_training_workflow_records",
    "kaizo_digital_twin_history",
    "kaizo_decision_state_links",
    "kaizo_coach_decision_cycles",
    "kaizo_coach_progression_rules",
    "kaizo_coach_progression_evaluations",
    "kaizo_coach_session_constraints",
    "kaizo_coach_drill_library",
    "kaizo_coach_problem_drill_links",
)

COACH_EVIDENCE_TABLES = (
    "kaizo_coach_scoped_knowledge",
    "kaizo_coach_scoped_knowledge_links",
    "kaizo_coach_scoped_actor_trace",
    "kaizo_coach_scoped_governance",
)


def verify_required_tables(required_tables):
    names = tuple(dict.fromkeys(required_tables))
    if not names:
        return
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT " + ", ".join("to_regclass(%s)" for _ in names),
                names,
            )
            row = cur.fetchone()
    values = row if row is not None else (None,) * len(names)
    missing = [name for name, value in zip(names, values) if value is None]
    if missing:
        raise RuntimeError("Required pre-provisioned Staging tables are missing: " + ", ".join(missing))
    return names
