from __future__ import annotations

import uuid
import pytest

import persistence
from productization import (
    coach_assessment_workflow,
    coach_decision_workflow,
    coach_diagnostic_workflow,
    coach_problem_workflow,
    coach_progression_workflow,
    coach_roster,
    coach_training_workflow,
)


pytestmark = pytest.mark.skipif(
    not persistence.is_postgres_enabled(),
    reason="requires disposable PostgreSQL service",
)


def _drill_fields():
    return {
        "name": "Uchi-komi entry drill", "judo_area": "Nage-waza",
        "technical_skill": "Seoi-nage entry", "problem_target": "Late entry under resistance",
        "decision_target": "Select entry timing after grip stabilization",
        "age_suitability": "U15", "skill_level": "Intermediate",
        "execution_pattern": "Kumi-kata to entry with progressive resistance",
        "coach_cues": ["Maintain posture"], "common_errors": ["Late step"],
        "correction": "Reduce cue count and retest timing.",
        "dosage": "3 x 8 quality repetitions", "intensity": "Moderate",
        "rest": "45 seconds", "partner_requirement": "Matched partner",
        "equipment": "Judogi", "safety_constraints": "Controlled entry; stop on pain.",
        "kpi": "Successful entry percentage", "retest_link": "entry_quality",
        "competition_randori_transfer": "Constrained randori transfer.",
    }


def _scope():
    persistence.initialize()
    tenant = "TENANT-" + uuid.uuid4().hex
    coach = "auth0|coach-" + uuid.uuid4().hex
    athlete = coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=coach, display_name="Progression Athlete")
    assessment = coach_assessment_workflow.create_assessment(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        template_id="PROGRESSION-BASELINE", measurements={"entry_quality": 7})
    problem = coach_problem_workflow.create_problem_statement(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        assessment_id=assessment["assessment_id"],
        statement="Late entry under resistance", problem_type="technical_execution")
    evidence = {
        "evidence_id": "EVID-" + uuid.uuid4().hex,
        "subject_type": "assessment", "subject_id": assessment["assessment_id"],
        "evidence_level": "E3", "status": "VERIFIED",
        "source_ref": "assessment://progression-postgres-test",
        "claim": "Entry quality measured.", "observed_value": {"entry_quality": 7},
        "verified_by": "trusted-test-fixture", "verified_at": "2026-11-10T00:00:00Z",
        "notes": None,
    }
    persistence.upsert_evidence(evidence)
    diagnosis = coach_diagnostic_workflow.create_evidence_linked_diagnosis(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        problem_id=problem["problem_id"], evidence_ids=[evidence["evidence_id"]],
        diagnosis="Entry timing breakdown.", confidence="HIGH")
    candidates = coach_decision_workflow.generate_decision_candidates(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        diagnosis_id=diagnosis["diagnosis_id"])["candidates"]
    coach_decision_workflow.review_decision_candidate(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        candidate_id=candidates[0]["candidate_id"], action="CONFIRM")
    decision = coach_decision_workflow.record_coach_decision(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        candidate_id=candidates[0]["candidate_id"],
        outcome_intent="Improve entry timing under resistance.")
    plan = coach_training_workflow.create_training_plan(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        decision_id=decision["decision_id"], title="Entry plan", objective="Improve entry quality")
    session = coach_training_workflow.create_training_session(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete["athlete_id"],
        plan_id=plan["plan_id"], title="Session 1", duration_minutes=40,
        blocks=[{"name":"Uchi-komi", "duration_minutes":20},
                {"name":"Randori", "duration_minutes":20}])
    return tenant, coach, athlete["athlete_id"], assessment["assessment_id"], problem["problem_id"], evidence, plan, session


def _rule(scope):
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, plan, session = scope
    return coach_progression_workflow.create_progression_rule(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        plan_id=plan["plan_id"], name="Entry quality progression",
        metric="entry_quality", operator="GTE", threshold=8,
        action="PROGRESS", adjustment=1, rule_version="1.0.0",
        evidence_ids=[evidence["evidence_id"]])


def _drill(scope):
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, plan, session = scope
    return coach_progression_workflow.create_drill(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        assessment_id=assessment_id, drill_fields=_drill_fields(),
        evidence_ids=[evidence["evidence_id"]],
        source_refs=["coach-observation://entry-timing"])


def test_postgres_progression_rule_approval_and_evaluation_are_advisory():
    scope = _scope()
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, plan, session = scope
    rule = _rule(scope)
    assert rule["approval_status"] == "DRAFT"
    with pytest.raises(coach_progression_workflow.CoachProgressionConflict):
        coach_progression_workflow.evaluate_progression_rule(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            rule_id=rule["rule_id"], observed_value=9)
    approved = coach_progression_workflow.approve_progression_rule(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        rule_id=rule["rule_id"])
    assert approved["approval_status"] == "APPROVED"
    assert approved["approved_by"] == coach
    evaluation = coach_progression_workflow.evaluate_progression_rule(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        rule_id=rule["rule_id"], observed_value=9)
    assert evaluation["matched"] is True
    assert evaluation["recommended_action"] == "PROGRESS"
    assert evaluation["execution_authorized"] is False
    assert len(coach_progression_workflow.list_progression_evaluations(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        rule_id=rule["rule_id"])) == 1
    assert coach_progression_workflow.list_progression_rules(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        plan_id=plan["plan_id"])[0]["name"] == "Entry quality progression"


def test_postgres_session_constraint_drill_review_and_problem_drill_link():
    scope = _scope()
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, plan, session = scope
    item = coach_progression_workflow.create_session_constraint(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        session_id=session["session_id"], kind="CONSTRAINT",
        content="No uncontrolled high-amplitude throws.", priority="HIGH")
    assert item["created_by"] == coach
    assert coach_progression_workflow.list_session_constraints(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        session_id=session["session_id"]) == [item]

    drill = _drill(scope)
    assert drill["status"] == "DRAFT" and drill["coach_review"] is False
    assert coach_progression_workflow.list_drills(
        tenant_id=tenant, coach_actor_id=coach) == []
    approved = coach_progression_workflow.approve_drill(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        drill_id=drill["drill_id"])
    assert approved["status"] == "PUBLISHED" and approved["coach_review"] is True
    assert len(coach_progression_workflow.list_drills(
        tenant_id=tenant, coach_actor_id=coach)) == 1

    link = coach_progression_workflow.create_problem_drill_link(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        problem_id=problem_id, drill_id=drill["drill_id"],
        rationale="Drill targets the diagnosed entry timing issue.",
        evidence_ids=[evidence["evidence_id"]])
    assert link["created_by"] == coach
    assert link["execution_authorized"] is False
    assert coach_progression_workflow.list_problem_drill_links(
        tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
        problem_id=problem_id) == [link]
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*) FROM kaizo_audit_logs
                   WHERE tenant_id=%s AND who=%s AND action IN
                     ('COACH_PROGRESSION_RULE_CREATED','COACH_SESSION_CONSTRAINT_NOTE_CREATED',
                      'COACH_DRILL_CREATED','COACH_DRILL_APPROVED','COACH_PROBLEM_DRILL_LINK_CREATED')""",
                (tenant, coach))
            assert cur.fetchone()[0] >= 4


@pytest.mark.parametrize("operation,table", [
    ("rule", "kaizo_coach_progression_rules"),
    ("constraint", "kaizo_coach_session_constraints"),
    ("drill", "kaizo_coach_drill_library"),
    ("link", "kaizo_coach_problem_drill_links"),
])
def test_postgres_audit_failure_rolls_back_progression_and_drill_writes(monkeypatch, operation, table):
    scope = _scope()
    tenant, coach, athlete_id, assessment_id, problem_id, evidence, plan, session = scope
    drill = _drill(scope) if operation == "link" else None
    if operation == "link":
        drill = coach_progression_workflow.approve_drill(
            tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
            drill_id=drill["drill_id"])

    def fail_audit(**kwargs):
        raise RuntimeError("injected audit failure")

    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    with pytest.raises(RuntimeError, match="injected audit failure"):
        if operation == "rule":
            _rule(scope)
        elif operation == "constraint":
            coach_progression_workflow.create_session_constraint(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                session_id=session["session_id"], kind="NOTE", content="Rollback", priority="LOW")
        elif operation == "drill":
            _drill(scope)
        else:
            coach_progression_workflow.create_problem_drill_link(
                tenant_id=tenant, coach_actor_id=coach, athlete_id=athlete_id,
                problem_id=problem_id, drill_id=drill["drill_id"],
                rationale="Rollback link", evidence_ids=[evidence["evidence_id"]])
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            if operation == "rule":
                cur.execute("SELECT COUNT(*) FROM kaizo_coach_progression_rules WHERE plan_id=%s", (plan["plan_id"],))
            elif operation == "constraint":
                cur.execute("SELECT COUNT(*) FROM kaizo_coach_session_constraints WHERE session_id=%s", (session["session_id"],))
            elif operation == "drill":
                cur.execute("SELECT COUNT(*) FROM kaizo_coach_drill_library WHERE source_assessment_id=%s", (assessment_id,))
            else:
                cur.execute("SELECT COUNT(*) FROM kaizo_coach_problem_drill_links WHERE problem_id=%s", (problem_id,))
            assert cur.fetchone()[0] == 0
