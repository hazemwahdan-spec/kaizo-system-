from __future__ import annotations

from fastapi.testclient import TestClient

import main
import persistence
from productization import (
    coach_assessment_workflow,
    coach_decision_workflow,
    coach_diagnostic_workflow,
    coach_problem_workflow,
    coach_roster,
    coach_training_workflow,
    product_api,
)
from productization.identity import Principal


def _principal(actor: str, tenant: str) -> Principal:
    return Principal(actor_id=actor, role="coach", tenant_id=tenant,
                     resource_owner_id=None, verified=True, source="oidc_jwt", permissions=frozenset({"product"}))


def _setup(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_PERSISTENCE_MODE", "memory")
    monkeypatch.delenv("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", raising=False)
    coach_roster.reset_memory_state()
    coach_assessment_workflow.reset_memory_state()
    coach_problem_workflow._MEMORY.clear()
    coach_problem_workflow._MEMORY_AUDIT.clear()
    coach_diagnostic_workflow.reset_memory_state()
    coach_decision_workflow.reset_memory_state()
    coach_training_workflow.reset_memory_state()
    principals = {
        "coach-a": _principal("auth0|coach-a", "ACADEMY-A"),
        "coach-b": _principal("auth0|coach-b", "ACADEMY-A"),
        "coach-c": _principal("auth0|coach-c", "ACADEMY-B"),
    }

    def resolve(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise product_api.IdentityNotConfiguredError("Bearer authentication is required")
        token = authorization.removeprefix("Bearer ")
        if token not in principals:
            raise product_api.IdentityNotConfiguredError("unknown test token")
        return principals[token]

    monkeypatch.setattr(product_api, "resolve_bearer_principal", resolve)
    client = TestClient(main.app)
    headers = {key: {"Authorization": f"Bearer {key}"} for key in principals}
    athletes, decisions, evidence = {}, {}, {}
    monkeypatch.setattr(persistence, "get_evidence", lambda evidence_id: evidence.get(evidence_id))
    for key in principals:
        tenant, actor = ("ACADEMY-B", "auth0|coach-c") if key == "coach-c" else ("ACADEMY-A", "auth0|" + key)
        athlete = coach_roster.create_owned_athlete(
            tenant_id=tenant, coach_actor_id=actor, display_name="Training athlete " + key)
        athletes[key] = athlete
        assessment = coach_assessment_workflow.create_assessment(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            template_id="TRAINING-BASELINE-" + key, measurements={"entry_quality": 7})
        problem = coach_problem_workflow.create_problem_statement(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            assessment_id=assessment["assessment_id"],
            statement="Entry timing degrades under resistance.", problem_type="technical_execution")
        evidence_id = "TRAINING-EVIDENCE-" + key
        evidence[evidence_id] = {
            "evidence_id": evidence_id, "subject_type": "assessment",
            "subject_id": assessment["assessment_id"], "evidence_level": "E3",
            "status": "VERIFIED", "source_ref": "assessment://training-test",
            "claim": "Late entry observed.", "observed_value": {"count": 4},
            "verified_by": "trusted-fixture", "verified_at": "2026-11-10T00:00:00Z",
            "notes": None,
        }
        diagnosis = coach_diagnostic_workflow.create_evidence_linked_diagnosis(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            problem_id=problem["problem_id"], evidence_ids=[evidence_id],
            diagnosis="Timing breakdown under resistance.", confidence="HIGH")
        candidates = coach_decision_workflow.generate_decision_candidates(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            diagnosis_id=diagnosis["diagnosis_id"])["candidates"]
        coach_decision_workflow.review_decision_candidate(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            candidate_id=candidates[0]["candidate_id"], action="CONFIRM")
        decisions[key] = coach_decision_workflow.record_coach_decision(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            candidate_id=candidates[0]["candidate_id"],
            outcome_intent="Improve successful entry under resistance.")
    return client, headers, athletes, decisions


def test_plan_requires_owned_coach_reviewed_decision_and_is_draft(monkeypatch):
    client, headers, athletes, decisions = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/training-plans"
    forged = {**headers["coach-a"], "X-KAIZO-Actor": "attacker",
              "X-KAIZO-Role": "administrator", "X-KAIZO-Tenant": "ACADEMY-B"}
    created = client.post(path, headers=forged, json={
        "decision_id": decisions["coach-a"]["decision_id"],
        "title": "Entry timing plan", "objective": "Improve entry quality",
        "constraints": {"duration_minutes": 60}, "created_by": "forged-client"})
    assert created.status_code == 201, created.text
    plan = created.json()
    assert plan["status"] == "DRAFT"
    assert plan["created_by"] == "auth0|coach-a"
    assert plan["coach_final_authority"] is True
    assert plan["execution_authorized"] is False
    read = client.get(path + "/" + plan["plan_id"], headers=headers["coach-a"])
    assert read.status_code == 200 and read.json()["plan_id"] == plan["plan_id"]
    listed = client.get(path, headers=headers["coach-a"])
    assert listed.status_code == 200
    assert [x["plan_id"] for x in listed.json()["training_plans"]] == [plan["plan_id"]]
    assert client.get(path + "/" + plan["plan_id"], headers=headers["coach-b"]).status_code == 404
    assert client.get(path + "/" + plan["plan_id"], headers=headers["coach-c"]).status_code == 404
    assert coach_training_workflow._MEMORY_AUDIT[0]["who"] == "auth0|coach-a"


def test_session_structure_and_dosage_are_scoped_and_draft(monkeypatch):
    client, headers, athletes, decisions = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    plan_path = f"/api/v1/product/coach/athletes/{athlete_id}/training-plans"
    plan = client.post(plan_path, headers=headers["coach-a"], json={
        "decision_id": decisions["coach-a"]["decision_id"],
        "title": "Entry timing plan", "objective": "Improve entry quality"}).json()
    session_path = f"/api/v1/product/coach/athletes/{athlete_id}/training-plans/{plan['plan_id']}/sessions"
    blocks = [
        {"name": "Uchi-komi timing", "duration_minutes": 20, "focus": "entry timing"},
        {"name": "Resistance randori", "duration_minutes": 20, "focus": "decision transfer"},
    ]
    bad = client.post(session_path, headers=headers["coach-a"], json={
        "title": "Bad timing", "duration_minutes": 45, "blocks": blocks})
    assert bad.status_code == 400
    created = client.post(session_path, headers=headers["coach-a"], json={
        "title": "Session 1", "duration_minutes": 40, "blocks": blocks})
    assert created.status_code == 201, created.text
    session = created.json()
    assert session["status"] == "DRAFT"
    assert session["created_by"] == "auth0|coach-a"
    assert session["execution_authorized"] is False
    session_read_path = f"/api/v1/product/coach/athletes/{athlete_id}/training-sessions/{session['session_id']}"
    assert client.get(session_read_path, headers=headers["coach-a"]).status_code == 200
    assert len(client.get(session_path, headers=headers["coach-a"]).json()["sessions"]) == 1

    dosage_path = session_read_path + "/dosage"
    wrong_block = client.post(dosage_path, headers=headers["coach-a"], json={
        "block_name": "Not a session block", "sets": 3, "reps": 10, "rest_seconds": 30})
    assert wrong_block.status_code == 400
    bad_dosage = client.post(dosage_path, headers=headers["coach-a"], json={
        "block_name": "Uchi-komi timing", "sets": 0, "reps": 10, "rest_seconds": 30})
    assert bad_dosage.status_code == 400
    dosage = client.post(dosage_path, headers=headers["coach-a"], json={
        "block_name": "Uchi-komi timing", "sets": 3, "reps": 10,
        "rest_seconds": 30, "dosage_notes": "Maintain quality."})
    assert dosage.status_code == 201, dosage.text
    assert dosage.json()["prescribed_by"] == "auth0|coach-a"
    assert dosage.json()["status"] == "DRAFT"
    assert dosage.json()["execution_authorized"] is False
    read = client.get(dosage_path, headers=headers["coach-a"])
    assert read.status_code == 200 and len(read.json()["dosages"]) == 1
    item = read.json()["dosages"][0]
    get_one = client.get(dosage_path + "/" + item["dosage_id"], headers=headers["coach-a"])
    assert get_one.status_code == 200 and get_one.json()["dosage_id"] == item["dosage_id"]
    assert client.get(dosage_path, headers=headers["coach-b"]).status_code == 404


def test_training_plan_rejects_missing_or_cross_scope_decision_and_anonymous(monkeypatch):
    client, headers, athletes, decisions = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/training-plans"
    missing = client.post(path, headers=headers["coach-a"], json={
        "decision_id": "missing", "title": "Plan", "objective": "Objective"})
    assert missing.status_code == 404
    cross = client.post(path, headers=headers["coach-b"], json={
        "decision_id": decisions["coach-a"]["decision_id"], "title": "Plan", "objective": "Objective"})
    assert cross.status_code == 404
    assert client.post(path, json={
        "decision_id": decisions["coach-a"]["decision_id"], "title": "Plan", "objective": "Objective"}).status_code == 401


def test_training_session_requires_unique_named_blocks_and_exact_duration(monkeypatch):
    client, headers, athletes, decisions = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    plan_path = f"/api/v1/product/coach/athletes/{athlete_id}/training-plans"
    plan = client.post(plan_path, headers=headers["coach-a"], json={
        "decision_id": decisions["coach-a"]["decision_id"],
        "title": "Plan", "objective": "Objective"}).json()
    path = plan_path + f"/{plan['plan_id']}/sessions"
    duplicate = client.post(path, headers=headers["coach-a"], json={
        "title": "Session", "duration_minutes": 20,
        "blocks": [{"name": "Same", "duration_minutes": 10}, {"name": "Same", "duration_minutes": 10}]})
    assert duplicate.status_code == 400
