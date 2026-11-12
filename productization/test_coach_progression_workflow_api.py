from __future__ import annotations

from fastapi.testclient import TestClient

import main
import persistence
from productization import (
    coach_assessment_workflow,
    coach_decision_workflow,
    coach_diagnostic_workflow,
    coach_problem_workflow,
    coach_progression_workflow,
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
    coach_progression_workflow.reset_memory_state()
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
    evidence, resources = {}, {}
    monkeypatch.setattr(persistence, "get_evidence", lambda evidence_id: evidence.get(evidence_id))
    for key in principals:
        tenant, actor = ("ACADEMY-B", "auth0|coach-c") if key == "coach-c" else ("ACADEMY-A", "auth0|" + key)
        athlete = coach_roster.create_owned_athlete(
            tenant_id=tenant, coach_actor_id=actor, display_name="Progression athlete " + key)
        assessment = coach_assessment_workflow.create_assessment(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            template_id="PROGRESSION-BASELINE-" + key, measurements={"entry_quality": 7})
        problem = coach_problem_workflow.create_problem_statement(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            assessment_id=assessment["assessment_id"],
            statement="Entry timing degrades under resistance.", problem_type="technical_execution")
        evidence_id = "PROGRESSION-EVIDENCE-" + key
        evidence[evidence_id] = {
            "evidence_id": evidence_id, "subject_type": "assessment",
            "subject_id": assessment["assessment_id"], "evidence_level": "E3",
            "status": "VERIFIED", "source_ref": "assessment://progression-test",
            "claim": "Entry quality measured.", "observed_value": {"entry_quality": 7},
            "verified_by": "trusted-fixture", "verified_at": "2026-11-10T00:00:00Z",
            "notes": None,
        }
        diagnosis = coach_diagnostic_workflow.create_evidence_linked_diagnosis(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            problem_id=problem["problem_id"], evidence_ids=[evidence_id],
            diagnosis="Entry timing breakdown.", confidence="HIGH")
        candidates = coach_decision_workflow.generate_decision_candidates(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            diagnosis_id=diagnosis["diagnosis_id"])["candidates"]
        coach_decision_workflow.review_decision_candidate(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            candidate_id=candidates[0]["candidate_id"], action="CONFIRM")
        decision = coach_decision_workflow.record_coach_decision(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            candidate_id=candidates[0]["candidate_id"],
            outcome_intent="Improve entry timing under resistance.")
        plan = coach_training_workflow.create_training_plan(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            decision_id=decision["decision_id"], title="Entry plan",
            objective="Improve entry quality")
        session = coach_training_workflow.create_training_session(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athlete["athlete_id"],
            plan_id=plan["plan_id"], title="Session 1", duration_minutes=40,
            blocks=[{"name":"Uchi-komi", "duration_minutes":20},
                    {"name":"Randori", "duration_minutes":20}])
        resources[key] = {
            "athlete": athlete, "assessment": assessment, "problem": problem,
            "diagnosis": diagnosis, "decision": decision, "plan": plan,
            "session": session, "evidence_id": evidence_id,
        }
    return client, headers, resources, evidence


def _drill_payload(resource, name="Uchi-komi entry drill"):
    return {
        "assessment_id": resource["assessment"]["assessment_id"],
        "name": name, "judo_area": "Nage-waza", "technical_skill": "Seoi-nage entry",
        "problem_target": "Late entry under resistance",
        "decision_target": "Select entry timing after grip stabilization",
        "age_suitability": "U15", "skill_level": "Intermediate",
        "execution_pattern": "Kumi-kata to entry with progressive resistance",
        "coach_cues": ["Maintain posture", "Enter on opponent movement"],
        "common_errors": ["Late step", "Pulling without kuzushi"],
        "correction": "Reduce cue count and retest timing.",
        "dosage": "3 x 8 quality repetitions", "intensity": "Moderate",
        "rest": "45 seconds", "partner_requirement": "Matched partner",
        "equipment": "Judogi", "safety_constraints": "Controlled entry; stop on pain.",
        "kpi": "Successful entry percentage", "retest_link": "Assessment KPI: entry_quality",
        "competition_randori_transfer": "Use the entry during constrained randori.",
        "evidence_ids": [resource["evidence_id"]],
        "source_refs": ["coach-observation://entry-timing"],
    }


def test_progression_rule_requires_evidence_approval_and_advisory_evaluation(monkeypatch):
    client, headers, resources, evidence = _setup(monkeypatch)
    r = resources["coach-a"]
    athlete_id = r["athlete"]["athlete_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/training-plans/{r['plan']['plan_id']}/progression-rules"
    created = client.post(path, headers=headers["coach-a"], json={
        "name": "Entry quality progression", "metric": "entry_quality",
        "operator": "GTE", "threshold": 8, "action": "PROGRESS",
        "adjustment": 1, "rule_version": "1.0.0",
        "evidence_ids": [r["evidence_id"]], "created_by": "forged-client"})
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["approval_status"] == "DRAFT"
    assert rule["created_by"] == "auth0|coach-a"
    eval_path = f"/api/v1/product/coach/athletes/{athlete_id}/progression-rules/{rule['rule_id']}/evaluations"
    before = client.post(eval_path, headers=headers["coach-a"], json={"observed_value": 9})
    assert before.status_code == 409
    approve_path = f"/api/v1/product/coach/athletes/{athlete_id}/progression-rules/{rule['rule_id']}/coach-approval"
    approved = client.post(approve_path, headers=headers["coach-a"])
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_status"] == "APPROVED"
    evaluated = client.post(eval_path, headers=headers["coach-a"], json={"observed_value": 9})
    assert evaluated.status_code == 201, evaluated.text
    assert evaluated.json()["matched"] is True
    assert evaluated.json()["recommended_action"] == "PROGRESS"
    assert evaluated.json()["execution_authorized"] is False
    hold = client.post(eval_path, headers=headers["coach-a"], json={"observed_value": 6})
    assert hold.status_code == 201 and hold.json()["recommended_action"] == "HOLD"
    assert len(client.get(eval_path, headers=headers["coach-a"]).json()["evaluations"]) == 2
    assert client.get(path, headers=headers["coach-b"]).status_code == 404


def test_session_constraints_notes_are_owned_and_audited(monkeypatch):
    client, headers, resources, evidence = _setup(monkeypatch)
    r = resources["coach-a"]
    athlete_id, session_id = r["athlete"]["athlete_id"], r["session"]["session_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/training-sessions/{session_id}/constraints-notes"
    forged = {**headers["coach-a"], "X-KAIZO-Actor":"attacker","X-KAIZO-Tenant":"ACADEMY-B"}
    created = client.post(path, headers=forged, json={
        "kind":"CONSTRAINT","content":"No uncontrolled high-amplitude throws in this block.",
        "priority":"HIGH","created_by":"forged-client"})
    assert created.status_code == 201, created.text
    assert created.json()["created_by"] == "auth0|coach-a"
    assert created.json()["execution_authorized"] is False
    listed = client.get(path, headers=headers["coach-a"])
    assert listed.status_code == 200 and len(listed.json()["constraints_notes"]) == 1
    assert client.get(path, headers=headers["coach-b"]).status_code == 404
    invalid = client.post(path, headers=headers["coach-a"], json={
        "kind":"UNSAFE","content":"Invalid kind","priority":"HIGH"})
    assert invalid.status_code == 400


def test_drill_library_requires_verified_evidence_and_explicit_coach_review(monkeypatch):
    client, headers, resources, evidence = _setup(monkeypatch)
    r = resources["coach-a"]
    athlete_id = r["athlete"]["athlete_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/drill-library"
    created = client.post(path, headers=headers["coach-a"], json=_drill_payload(r))
    assert created.status_code == 201, created.text
    drill = created.json()
    assert drill["status"] == "DRAFT"
    assert drill["coach_review"] is False
    assert drill["execution_authorized"] is False
    assert client.get("/api/v1/product/coach/drill-library", headers=headers["coach-a"]).json()["drills"] == []
    drafts = client.get("/api/v1/product/coach/drill-library?include_drafts=true", headers=headers["coach-a"])
    assert len(drafts.json()["drills"]) == 1
    review_path = path + f"/{drill['drill_id']}/coach-review"
    approved = client.post(review_path, headers=headers["coach-a"])
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "PUBLISHED"
    assert approved.json()["coach_review"] is True
    assert approved.json()["approved_by"] == "auth0|coach-a"
    assert len(client.get("/api/v1/product/coach/drill-library", headers=headers["coach-a"]).json()["drills"]) == 1
    bad = _drill_payload(r, "Missing evidence drill")
    bad["evidence_ids"] = ["missing-evidence"]
    missing = client.post(path, headers=headers["coach-a"], json=bad)
    assert missing.status_code == 404


def test_problem_to_drill_link_requires_published_drill_and_same_scope_evidence(monkeypatch):
    client, headers, resources, evidence = _setup(monkeypatch)
    r = resources["coach-a"]
    athlete_id = r["athlete"]["athlete_id"]
    drill_path = f"/api/v1/product/coach/athletes/{athlete_id}/drill-library"
    drill = client.post(drill_path, headers=headers["coach-a"], json=_drill_payload(r)).json()
    link_path = f"/api/v1/product/coach/athletes/{athlete_id}/problems/{r['problem']['problem_id']}/drill-links"
    not_published = client.post(link_path, headers=headers["coach-a"], json={
        "drill_id":drill["drill_id"],"rationale":"Match the drill to the diagnosed entry problem.",
        "evidence_ids":[r["evidence_id"]]})
    assert not_published.status_code == 409
    assert client.post(drill_path + f"/{drill['drill_id']}/coach-review", headers=headers["coach-a"]).status_code == 200
    linked = client.post(link_path, headers=headers["coach-a"], json={
        "drill_id":drill["drill_id"],"rationale":"Targets the diagnosed entry timing issue.",
        "evidence_ids":[r["evidence_id"]]})
    assert linked.status_code == 201, linked.text
    assert linked.json()["created_by"] == "auth0|coach-a"
    assert linked.json()["execution_authorized"] is False
    assert len(client.get(link_path, headers=headers["coach-a"]).json()["drill_links"]) == 1
    assert client.get(link_path, headers=headers["coach-b"]).status_code == 404
    cross = client.post(link_path, headers=headers["coach-a"], json={
        "drill_id":drill["drill_id"],"rationale":"Cross evidence should fail.",
        "evidence_ids":["PROGRESSION-EVIDENCE-coach-b"]})
    assert cross.status_code == 409


def test_progression_drill_and_constraint_apis_require_bearer_and_hide_legacy_routes(monkeypatch):
    client, headers, resources, evidence = _setup(monkeypatch)
    r = resources["coach-a"]
    athlete_id = r["athlete"]["athlete_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/training-plans/{r['plan']['plan_id']}/progression-rules"
    assert client.post(path, json={
        "name":"No auth","metric":"entry_quality","operator":"GTE","threshold":8,
        "action":"PROGRESS","adjustment":1,"rule_version":"1.0.0",
        "evidence_ids":[r["evidence_id"]]}).status_code == 401
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/product/coach/drill-library" in paths
    assert "/api/v1/product/coach/athletes/{athlete_id}/problems/{problem_id}/drill-links" in paths
    assert "/api/v1/progression-rules" not in paths
    assert "/api/v1/drill-library" not in paths
