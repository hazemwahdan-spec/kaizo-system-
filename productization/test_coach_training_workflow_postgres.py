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
    coach_training_workflow,
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
        tenant_id=tenant, coach_actor_id=coach, display_name="Training Workflow Athlete")
    assessment = coach_assessment_workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        template_id="TRAINING-BASELINE", measurements={"entry_quality": 7})
    problem = coach_problem_workflow.create_problem_statement(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        assessment_id=assessment["assessment_id"],
        statement="Late entry under resistance", problem_type="technical_execution")
    evidence = {
        "evidence_id": "EVID-" + uuid.uuid4().hex,
        "subject_type": "assessment", "subject_id": assessment["assessment_id"],
        "evidence_level": "E3", "status": "VERIFIED",
        "source_ref": "assessment://training-postgres-test",
        "claim": "Late entry observed repeatedly.", "observed_value": {"count": 4},
        "verified_by": "trusted-test-fixture", "verified_at": "2026-11-10T00:00:00Z",
        "notes": None,
    }
    persistence.upsert_evidence(evidence)
    diagnosis = coach_diagnostic_workflow.create_evidence_linked_diagnosis(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        problem_id=problem["problem_id"], evidence_ids=[evidence["evidence_id"]],
        diagnosis="Timing breakdown under resistance.", confidence="HIGH")
    candidates = coach_decision_workflow.generate_decision_candidates(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        diagnosis_id=diagnosis["diagnosis_id"])["candidates"]
    coach_decision_workflow.review_decision_candidate(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        candidate_id=candidates[0]["candidate_id"], action="CONFIRM")
    decision = coach_decision_workflow.record_coach_decision(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        candidate_id=candidates[0]["candidate_id"],
        outcome_intent="Improve successful entry under resistance.")
    return tenant, coach, athlete["athlete_id"], decision


def _plan(scope):
    tenant, coach, athlete_id, decision = scope
    return coach_training_workflow.create_training_plan(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        decision_id=decision["decision_id"], title="Entry timing plan",
        objective="Improve entry quality", constraints={"duration_minutes": 60})


def _session(scope, plan):
    tenant, coach, athlete_id, decision = scope
    return coach_training_workflow.create_training_session(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        plan_id=plan["plan_id"], title="Session 1", duration_minutes=40,
        blocks=[
            {"name": "Uchi-komi timing", "duration_minutes": 20},
            {"name": "Resistance randori", "duration_minutes": 20},
        ])


def test_postgres_plan_session_and_dosage_persist_with_owned_lineage(monkeypatch):
    scope = _scope()
    tenant, coach, athlete_id, decision = scope
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.kaizo_training_dosages')")
            assert cur.fetchone()[0] is not None

    def unexpected_request_ddl():
        raise AssertionError("training dosage schema DDL must run only during persistence.initialize()")

    monkeypatch.setattr(persistence, "_ensure_training_dosages_table", unexpected_request_ddl)
    plan = _plan(scope)
    assert plan["status"] == "DRAFT"
    assert plan["created_by"] == coach
    assert plan["execution_authorized"] is False
    assert coach_training_workflow.get_training_plan(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        plan_id=plan["plan_id"])["decision_id"] == decision["decision_id"]
    assert coach_training_workflow.list_training_plans(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id)[0]["plan_id"] == plan["plan_id"]
    assert coach_training_workflow.get_training_plan(
        tenant_id=tenant, coach_actor_id="auth0|other", athlete_id=athlete_id,
        plan_id=plan["plan_id"]) is None

    session = _session(scope, plan)
    assert session["status"] == "DRAFT"
    assert session["execution_authorized"] is False
    assert coach_training_workflow.get_training_session(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        session_id=session["session_id"])["plan_id"] == plan["plan_id"]
    assert coach_training_workflow.list_training_sessions(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        plan_id=plan["plan_id"])[0]["session_id"] == session["session_id"]

    dosage = coach_training_workflow.create_training_dosage(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        session_id=session["session_id"], block_name="Uchi-komi timing",
        sets=3, reps=10, rest_seconds=30, dosage_notes="Maintain quality.")
    assert dosage["status"] == "DRAFT"
    assert dosage["prescribed_by"] == coach
    assert dosage["execution_authorized"] is False
    assert coach_training_workflow.list_training_dosages(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        session_id=session["session_id"]) == [dosage]
    assert coach_training_workflow.get_training_dosage(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        session_id=session["session_id"], dosage_id=dosage["dosage_id"]) == dosage
    assert persistence.get_training_dosage(dosage["dosage_id"])["dosage_id"] == dosage["dosage_id"]
    assert persistence.list_training_dosages(session["session_id"])[0]["dosage_id"] == dosage["dosage_id"]
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s AND action IN
                     ('COACH_TRAINING_PLAN_CREATED','COACH_TRAINING_SESSION_CREATED','COACH_TRAINING_DOSAGE_PRESCRIBED')""",
                (tenant, coach))
            assert cur.fetchone()[0] == 3


@pytest.mark.parametrize("operation,table", [
    ("plan", "kaizo_training_plans"),
    ("session", "kaizo_training_sessions"),
    ("dosage", "kaizo_training_dosages"),
])
def test_postgres_audit_failure_rolls_back_training_writes(monkeypatch, operation, table):
    scope = _scope()
    tenant, coach, athlete_id, decision = scope
    plan = None if operation == "plan" else _plan(scope)
    session = None if operation in {"plan", "session"} else _session(scope, plan)
    if operation == "dosage":
        persistence._ensure_training_dosages_table()

    def fail_audit(**kwargs):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        if operation == "plan":
            _plan(scope)
        elif operation == "session":
            _session(scope, plan)
        else:
            coach_training_workflow.create_training_dosage(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                session_id=session["session_id"], block_name="Uchi-komi timing",
                sets=2, reps=8, rest_seconds=30)
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            if operation == "plan":
                cur.execute("SELECT COUNT(*) FROM kaizo_training_plans WHERE decision_id=%s",
                            (decision["decision_id"],))
            elif operation == "session":
                cur.execute("SELECT COUNT(*) FROM kaizo_training_sessions WHERE plan_id=%s",
                            (plan["plan_id"],))
            else:
                cur.execute("SELECT COUNT(*) FROM kaizo_training_dosages WHERE session_id=%s",
                            (session["session_id"],))
            assert cur.fetchone()[0] == 0


def test_postgres_session_rejects_wrong_block_duration_and_duplicate_names():
    scope = _scope()
    tenant, coach, athlete_id, decision = scope
    plan = _plan(scope)
    with pytest.raises(ValueError, match="block durations"):
        coach_training_workflow.create_training_session(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            plan_id=plan["plan_id"], title="Bad", duration_minutes=40,
            blocks=[{"name": "A", "duration_minutes": 10}])
    with pytest.raises(ValueError, match="distinct"):
        coach_training_workflow.create_training_session(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            plan_id=plan["plan_id"], title="Bad", duration_minutes=20,
            blocks=[{"name": "A", "duration_minutes": 10},
                    {"name": "A", "duration_minutes": 10}])


def test_postgres_dosage_requires_existing_block_and_valid_load():
    scope = _scope()
    tenant, coach, athlete_id, decision = scope
    plan = _plan(scope)
    session = _session(scope, plan)
    with pytest.raises(ValueError, match="existing session block"):
        coach_training_workflow.create_training_dosage(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            session_id=session["session_id"], block_name="Missing",
            sets=3, reps=10)
    with pytest.raises(ValueError, match="positive integers"):
        coach_training_workflow.create_training_dosage(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            session_id=session["session_id"], block_name="Uchi-komi timing",
            sets=0, reps=10)
