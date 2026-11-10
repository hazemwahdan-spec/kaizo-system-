from __future__ import annotations

import uuid
import pytest

import persistence
from productization import (
    coach_assessment_workflow,
    coach_decision_workflow,
    coach_diagnostic_workflow,
    coach_problem_workflow,
    coach_roster,
)


pytestmark = pytest.mark.skipif(
    not persistence.is_postgres_enabled(),
    reason="requires disposable PostgreSQL service",
)


def _scope():
    persistence.initialize()
    tenant = "TENANT-" + uuid.uuid4().hex
    coach = "auth0|coach-" + uuid.uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="Decision Workflow Athlete")
    assessment = coach_assessment_workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        template_id="DECISION-BASELINE", measurements={"entry_quality": 7})
    problem = coach_problem_workflow.create_problem_statement(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        assessment_id=assessment["assessment_id"],
        statement="Late entry under resistance", problem_type="technical_execution")
    evidence = {
        "evidence_id": "EVID-" + uuid.uuid4().hex,
        "subject_type": "assessment", "subject_id": assessment["assessment_id"],
        "evidence_level": "E3", "status": "VERIFIED",
        "source_ref": "assessment://decision-postgres-test",
        "claim": "Late entry observed repeatedly.", "observed_value": {"count": 4},
        "verified_by": "trusted-test-fixture", "verified_at": "2026-11-10T00:00:00Z",
        "notes": None,
    }
    persistence.upsert_evidence(evidence)
    diagnosis = coach_diagnostic_workflow.create_evidence_linked_diagnosis(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        problem_id=problem["problem_id"], evidence_ids=[evidence["evidence_id"]],
        diagnosis="Timing breakdown under resistance.", confidence="HIGH")
    return tenant, coach, athlete["athlete_id"], assessment["assessment_id"], problem["problem_id"], evidence, diagnosis


def _candidates(scope):
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, diagnosis = scope
    result = coach_decision_workflow.generate_decision_candidates(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        diagnosis_id=diagnosis["diagnosis_id"])
    assert result and len(result["candidates"]) == 3
    return result["candidates"]


def test_postgres_candidate_generation_is_scoped_idempotent_and_audited():
    scope = _scope()
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, diagnosis = scope
    first = _candidates(scope)
    second = coach_decision_workflow.generate_decision_candidates(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        diagnosis_id=diagnosis["diagnosis_id"])
    assert second["status"] == "CANDIDATES_ALREADY_EXIST"
    assert {x["candidate_id"] for x in first} == {x["candidate_id"] for x in second["candidates"]}
    listed = coach_decision_workflow.list_decision_candidates(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        diagnosis_id=diagnosis["diagnosis_id"])
    assert {x["candidate_id"] for x in listed} == {x["candidate_id"] for x in first}
    assert coach_decision_workflow.list_decision_candidates(
        tenant_id=tenant, coach_actor_id="auth0|other", athlete_id=athlete_id,
        diagnosis_id=diagnosis["diagnosis_id"]) is None
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s AND action='COACH_DECISION_CANDIDATES_GENERATED'""",
                (tenant, coach))
            assert cur.fetchone()[0] == 1


def test_postgres_rationale_comparison_review_and_decision_lineage():
    scope = _scope()
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, diagnosis = scope
    candidates = _candidates(scope)
    first = candidates[0]
    rationale = coach_decision_workflow.record_decision_rationale(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        candidate_id=first["candidate_id"], rationale="Evidence supports this option.",
        evidence_ids=[evidence["evidence_id"]])
    assert rationale["recorded_by"] == coach
    assert coach_decision_workflow.list_decision_rationales(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        candidate_id=first["candidate_id"]) == [rationale]
    with pytest.raises(coach_decision_workflow.CoachDecisionConflict):
        coach_decision_workflow.record_decision_rationale(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            candidate_id=first["candidate_id"], rationale="Cross resource",
            evidence_ids=["missing"])
    comparison = coach_decision_workflow.compare_decision_alternatives(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        diagnosis_id=diagnosis["diagnosis_id"],
        candidate_ids=[candidates[0]["candidate_id"], candidates[1]["candidate_id"]])
    assert comparison["comparison_status"] == "READY_FOR_COACH_REVIEW"
    assert coach_decision_workflow.list_decision_comparisons(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        diagnosis_id=diagnosis["diagnosis_id"]) == [comparison]
    with pytest.raises(coach_decision_workflow.CoachDecisionConflict):
        coach_decision_workflow.record_coach_decision(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            candidate_id=first["candidate_id"], outcome_intent="Improve timing")
    review = coach_decision_workflow.review_decision_candidate(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        candidate_id=first["candidate_id"], action="OVERRIDE",
        override_reason="Coach selects a safer constraint.")
    assert review["coach_final_authority"] is True
    assert review["execution_authorized"] is False
    assert coach_decision_workflow.list_candidate_reviews(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        candidate_id=first["candidate_id"]) == [review]
    decision = coach_decision_workflow.record_coach_decision(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        candidate_id=first["candidate_id"],
        outcome_intent="Improve successful entry under resistance.")
    assert decision["coach_action"] == "OVERRIDE"
    assert decision["execution_authorized"] is False
    assert coach_decision_workflow.list_decision_records(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        candidate_id=first["candidate_id"]) == [decision]


@pytest.mark.parametrize("operation,table", [
    ("candidates", "kaizo_decision_candidates"),
    ("rationale", "kaizo_decision_rationales"),
    ("comparison", "kaizo_decision_comparisons"),
    ("review", "kaizo_coach_decision_reviews"),
    ("decision", "kaizo_decision_records"),
])
def test_postgres_audit_failure_rolls_back_each_decision_write(monkeypatch, operation, table):
    scope = _scope()
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, diagnosis = scope
    candidates = [] if operation == "candidates" else _candidates(scope)
    candidate = candidates[0] if candidates else None
    if operation in {"comparison"}:
        candidate_ids = [x["candidate_id"] for x in candidates[:2]]
    if operation == "decision":
        coach_decision_workflow.review_decision_candidate(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            candidate_id=candidate["candidate_id"], action="CONFIRM")

    def fail_audit(**kwargs):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        if operation == "candidates":
            coach_decision_workflow.generate_decision_candidates(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                diagnosis_id=diagnosis["diagnosis_id"])
        elif operation == "rationale":
            coach_decision_workflow.record_decision_rationale(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                candidate_id=candidate["candidate_id"], rationale="Rollback",
                evidence_ids=[evidence["evidence_id"]])
        elif operation == "comparison":
            coach_decision_workflow.compare_decision_alternatives(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                diagnosis_id=diagnosis["diagnosis_id"], candidate_ids=candidate_ids)
        elif operation == "review":
            coach_decision_workflow.review_decision_candidate(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                candidate_id=candidate["candidate_id"], action="CONFIRM")
        else:
            coach_decision_workflow.record_coach_decision(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                candidate_id=candidate["candidate_id"], outcome_intent="Rollback")
    key = "diagnosis_id" if operation in {"candidates", "comparison"} else "candidate_id"
    value = diagnosis["diagnosis_id"] if key == "diagnosis_id" else candidate["candidate_id"]
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {key}=%s", (value,))
            count = cur.fetchone()[0]
    if operation == "candidates":
        assert count == 0
    elif operation == "rationale":
        assert count == 0
    elif operation == "comparison":
        assert count == 0
    elif operation == "review":
        assert count == 0
    else:
        assert count == 0
