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
    product_api,
)
from productization.identity import Principal


def _principal(actor: str, tenant: str) -> Principal:
    return Principal(actor_id=actor, role="coach", tenant_id=tenant,
                     resource_owner_id=None, verified=True, source="oidc_jwt")


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
    athletes, assessments, problems, diagnoses, evidence = {}, {}, {}, {}, {}
    monkeypatch.setattr(persistence, "get_evidence", lambda evidence_id: evidence.get(evidence_id))
    for key in principals:
        tenant, actor = ("ACADEMY-B", "auth0|coach-c") if key == "coach-c" else ("ACADEMY-A", "auth0|" + key)
        athletes[key] = coach_roster.create_owned_athlete(
            tenant_id=tenant, coach_actor_id=actor, display_name="Athlete " + key)
        assessments[key] = coach_assessment_workflow.create_assessment(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athletes[key]["athlete_id"],
            template_id="BASELINE-" + key, measurements={"entry_quality": 7})
        problems[key] = coach_problem_workflow.create_problem_statement(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athletes[key]["athlete_id"],
            assessment_id=assessments[key]["assessment_id"],
            statement="Entry timing degrades under resistance.", problem_type="technical_execution")
        evidence_id = "EVIDENCE-" + key
        evidence[evidence_id] = {
            "evidence_id": evidence_id, "subject_type": "assessment",
            "subject_id": assessments[key]["assessment_id"], "evidence_level": "E3",
            "status": "VERIFIED", "source_ref": "assessment://decision-test",
            "claim": "Late entry observed.", "observed_value": {"count": 4},
            "verified_by": "trusted-fixture", "verified_at": "2026-11-10T00:00:00Z",
            "notes": None,
        }
        diagnoses[key] = coach_diagnostic_workflow.create_evidence_linked_diagnosis(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athletes[key]["athlete_id"],
            problem_id=problems[key]["problem_id"], evidence_ids=[evidence_id],
            diagnosis="Timing breakdown under resistance.", confidence="HIGH")
    return client, headers, athletes, assessments, problems, diagnoses, evidence


def test_candidate_generation_is_scoped_idempotent_and_audited(monkeypatch):
    client, headers, athletes, assessments, problems, diagnoses, evidence = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    diagnosis_id = diagnoses["coach-a"]["diagnosis_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/diagnoses/{diagnosis_id}/decision-candidates"
    generated = client.post(path, headers=headers["coach-a"])
    assert generated.status_code == 201, generated.text
    body = generated.json()
    assert body["status"] == "CANDIDATES_GENERATED"
    assert len(body["candidates"]) == 3
    assert body["coach_review_required"] is True
    assert body["execution_authorized"] is False
    assert all(x["status"] == "PENDING_COACH_REVIEW" for x in body["candidates"])
    repeated = client.post(path, headers=headers["coach-a"])
    assert repeated.status_code == 201
    assert repeated.json()["status"] == "CANDIDATES_ALREADY_EXIST"
    assert len(repeated.json()["candidates"]) == 3
    read = client.get(path, headers=headers["coach-a"])
    assert read.status_code == 200 and {x["candidate_id"] for x in read.json()["candidates"]} == {x["candidate_id"] for x in first}
    assert client.get(path, headers=headers["coach-b"]).status_code == 404
    assert client.get(path, headers=headers["coach-c"]).status_code == 404
    assert coach_decision_workflow._MEMORY_AUDIT[0]["who"] == "auth0|coach-a"


def test_rationale_requires_same_scope_verified_evidence(monkeypatch):
    client, headers, athletes, assessments, problems, diagnoses, evidence = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    diagnosis_id = diagnoses["coach-a"]["diagnosis_id"]
    root = f"/api/v1/product/coach/athletes/{athlete_id}/diagnoses/{diagnosis_id}/decision-candidates"
    candidates = client.post(root, headers=headers["coach-a"]).json()["candidates"]
    candidate_id = candidates[0]["candidate_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/decision-candidates/{candidate_id}/rationales"
    good = client.post(path, headers=headers["coach-a"], json={
        "rationale": "The selected option addresses the observed timing breakdown.",
        "evidence_ids": ["EVIDENCE-coach-a"]})
    assert good.status_code == 201, good.text
    assert good.json()["recorded_by"] == "auth0|coach-a"
    assert good.json()["coach_review_required"] is True
    assert client.get(path, headers=headers["coach-a"]).json()["rationales"][0]["evidence_ids"] == ["EVIDENCE-coach-a"]
    wrong = client.post(path, headers=headers["coach-a"], json={
        "rationale": "Cross-athlete evidence must fail.", "evidence_ids": ["EVIDENCE-coach-b"]})
    assert wrong.status_code == 409
    assert client.get(path, headers=headers["coach-b"]).status_code == 404


def test_comparison_requires_two_distinct_candidates_from_same_diagnosis(monkeypatch):
    client, headers, athletes, assessments, problems, diagnoses, evidence = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    diagnosis_id = diagnoses["coach-a"]["diagnosis_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/diagnoses/{diagnosis_id}/decision-candidates"
    candidates = client.post(path, headers=headers["coach-a"]).json()["candidates"]
    comparison_path = f"/api/v1/product/coach/athletes/{athlete_id}/diagnoses/{diagnosis_id}/decision-comparisons"
    too_few = client.post(comparison_path, headers=headers["coach-a"], json={"candidate_ids":[candidates[0]["candidate_id"]]})
    assert too_few.status_code == 400
    duplicate = client.post(comparison_path, headers=headers["coach-a"], json={"candidate_ids":[candidates[0]["candidate_id"]]*2})
    assert duplicate.status_code == 400
    cross = client.post(comparison_path, headers=headers["coach-a"], json={"candidate_ids":[candidates[0]["candidate_id"],"missing"]})
    assert cross.status_code == 404
    valid = client.post(comparison_path, headers=headers["coach-a"], json={
        "candidate_ids":[candidates[0]["candidate_id"],candidates[1]["candidate_id"]]})
    assert valid.status_code == 201, valid.text
    assert valid.json()["comparison_status"] == "READY_FOR_COACH_REVIEW"
    assert valid.json()["execution_authorized"] is False
    assert len(client.get(comparison_path, headers=headers["coach-a"]).json()["comparisons"]) == 1


def test_coach_review_is_bearer_derived_and_required_before_decision(monkeypatch):
    client, headers, athletes, assessments, problems, diagnoses, evidence = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    diagnosis_id = diagnoses["coach-a"]["diagnosis_id"]
    root = f"/api/v1/product/coach/athletes/{athlete_id}/diagnoses/{diagnosis_id}/decision-candidates"
    candidates = client.post(root, headers=headers["coach-a"]).json()["candidates"]
    candidate_id = candidates[0]["candidate_id"]
    review_path = f"/api/v1/product/coach/athletes/{athlete_id}/decision-candidates/{candidate_id}/coach-review"
    decision_path = f"/api/v1/product/coach/athletes/{athlete_id}/decision-candidates/{candidate_id}/decision-record"
    before_review = client.post(decision_path, headers=headers["coach-a"], json={"outcome_intent":"Improve entry timing"})
    assert before_review.status_code == 409
    no_reason = client.post(review_path, headers=headers["coach-a"], json={"action":"OVERRIDE"})
    assert no_reason.status_code == 400
    forged = {**headers["coach-a"], "X-KAIZO-Actor":"attacker","X-KAIZO-Role":"admin","X-KAIZO-Tenant":"ACADEMY-B"}
    review = client.post(review_path, headers=forged, json={"action":"OVERRIDE","override_reason":"Coach selects a safer constraint."})
    assert review.status_code == 201, review.text
    assert review.json()["coach_id"] == "auth0|coach-a"
    assert review.json()["coach_final_authority"] is True
    assert review.json()["execution_authorized"] is False
    decision = client.post(decision_path, headers=headers["coach-a"], json={
        "outcome_intent":"Improve successful entry under resistance.",
        "decision_summary":"Use constraint-adjusted entry practice."})
    assert decision.status_code == 201, decision.text
    assert decision.json()["coach_id"] == "auth0|coach-a"
    assert decision.json()["coach_action"] == "OVERRIDE"
    assert decision.json()["execution_authorized"] is False
    assert client.get(decision_path, headers=headers["coach-a"]).json()["decisions"][0]["decision_id"] == decision.json()["decision_id"]
    assert client.get(decision_path, headers=headers["coach-b"]).status_code == 404


def test_decision_endpoints_require_bearer_and_hide_legacy_unscoped_paths(monkeypatch):
    client, headers, athletes, assessments, problems, diagnoses, evidence = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    diagnosis_id = diagnoses["coach-a"]["diagnosis_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/diagnoses/{diagnosis_id}/decision-candidates"
    assert client.post(path).status_code == 401
    paths = client.get("/openapi.json").json()["paths"]
    assert path in paths or "/api/v1/product/coach/athletes/{athlete_id}/diagnoses/{diagnosis_id}/decision-candidates" in paths
    assert "/api/v1/diagnoses/{diagnosis_id}/decision-candidates" not in paths
