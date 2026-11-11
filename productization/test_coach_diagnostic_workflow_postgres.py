from __future__ import annotations

import uuid
import pytest

import persistence
from productization import (
    coach_assessment_workflow,
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
        tenant_id=tenant, coach_actor_id=coach, display_name="Diagnostic Athlete")
    assessment = coach_assessment_workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        template_id="DIAGNOSTIC-BASELINE", measurements={"entry_quality": 7})
    problem = coach_problem_workflow.create_problem_statement(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        assessment_id=assessment["assessment_id"],
        statement="Late entry under resistance", problem_type="technical_execution")
    return tenant, coach, athlete["athlete_id"], assessment["assessment_id"], problem["problem_id"]


def _evidence(assessment_id, **overrides):
    item = {
        "evidence_id": "EVID-" + uuid.uuid4().hex,
        "subject_type": "assessment",
        "subject_id": assessment_id,
        "evidence_level": "E3",
        "status": "VERIFIED",
        "source_ref": "assessment://diagnostic-postgres-test",
        "claim": "Late entry observed repeatedly.",
        "observed_value": {"count": 4},
        "verified_by": "trusted-test-fixture",
        "verified_at": "2026-11-10T00:00:00Z",
        "notes": None,
    }
    item.update(overrides)
    persistence.upsert_evidence(item)
    return item


def test_postgres_cause_context_persists_scoped_and_audited():
    tenant, coach, athlete_id, assessment_id, problem_id = _scope()
    record = coach_diagnostic_workflow.create_cause_context_framing(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        problem_id=problem_id, cause="Grip acquisition is late.",
        context={"phase": "kumi-kata"},
        contributing_factors=["distance", "timing"])
    assert record["assessment_id"] == assessment_id
    assert coach_diagnostic_workflow.list_cause_context_framings(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        problem_id=problem_id) == [record]
    assert coach_diagnostic_workflow.list_cause_context_framings(
        tenant_id=tenant, coach_actor_id="auth0|other", athlete_id=athlete_id,
        problem_id=problem_id) is None
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s AND action='COACH_CAUSE_CONTEXT_FRAMED'""",
                (tenant, coach))
            assert cur.fetchone()[0] == 1


def test_postgres_diagnosis_requires_same_resource_verified_non_e0_evidence():
    tenant, coach, athlete_id, assessment_id, problem_id = _scope()
    evidence = _evidence(assessment_id)
    record = coach_diagnostic_workflow.create_evidence_linked_diagnosis(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        problem_id=problem_id, evidence_ids=[evidence["evidence_id"]],
        diagnosis="Timing breakdown under resistance", confidence="HIGH",
        resolution_state="RESOLVED")
    assert record["assessment_id"] == assessment_id
    assert coach_diagnostic_workflow.list_evidence_linked_diagnoses(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        problem_id=problem_id) == [record]
    assert coach_diagnostic_workflow.list_evidence_linked_diagnoses(
        tenant_id=tenant, coach_actor_id="auth0|other", athlete_id=athlete_id,
        problem_id=problem_id) is None

    wrong = _evidence("another-assessment")
    with pytest.raises(coach_diagnostic_workflow.CoachDiagnosticConflict):
        coach_diagnostic_workflow.create_evidence_linked_diagnosis(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            problem_id=problem_id, evidence_ids=[wrong["evidence_id"]],
            diagnosis="Cross-resource evidence")
    e0 = _evidence(assessment_id, evidence_level="E0")
    with pytest.raises(coach_diagnostic_workflow.CoachDiagnosticConflict):
        coach_diagnostic_workflow.create_evidence_linked_diagnosis(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            problem_id=problem_id, evidence_ids=[e0["evidence_id"]],
            diagnosis="E0 evidence")
    pending = _evidence(assessment_id, status="PENDING")
    with pytest.raises(coach_diagnostic_workflow.CoachDiagnosticConflict):
        coach_diagnostic_workflow.create_evidence_linked_diagnosis(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            problem_id=problem_id, evidence_ids=[pending["evidence_id"]],
            diagnosis="Unverified evidence")


@pytest.mark.parametrize("operation,action", [
    ("cause", "COACH_CAUSE_CONTEXT_FRAMED"),
    ("diagnosis", "COACH_EVIDENCE_LINKED_DIAGNOSIS_CREATED"),
])
def test_postgres_audit_failure_rolls_back_domain_write(monkeypatch, operation, action):
    tenant, coach, athlete_id, assessment_id, problem_id = _scope()
    evidence = _evidence(assessment_id)

    def fail_audit(**kwargs):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        if operation == "cause":
            coach_diagnostic_workflow.create_cause_context_framing(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                problem_id=problem_id, cause="Must roll back")
        else:
            coach_diagnostic_workflow.create_evidence_linked_diagnosis(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                problem_id=problem_id, evidence_ids=[evidence["evidence_id"]],
                diagnosis="Must roll back")
    table = "kaizo_cause_context_framings" if operation == "cause" else "kaizo_evidence_linked_diagnoses"
    id_column = "problem_id"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {id_column}=%s", (problem_id,))
            assert cur.fetchone()[0] == 0


def test_postgres_lost_ownership_prevents_diagnostic_write():
    tenant, coach, athlete_id, assessment_id, problem_id = _scope()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """DELETE FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s""",
                (tenant, coach, athlete_id))
        conn.commit()
    assert coach_diagnostic_workflow.create_cause_context_framing(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        problem_id=problem_id, cause="Ownership revoked") is None
