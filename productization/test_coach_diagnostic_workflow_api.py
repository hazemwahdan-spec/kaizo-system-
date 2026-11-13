from __future__ import annotations

from fastapi.testclient import TestClient

import main
import persistence
from productization import (
    coach_assessment_workflow,
    coach_diagnostic_workflow,
    coach_problem_workflow,
    coach_roster,
    product_api,
)
from productization.identity import Principal


def _principal(actor: str, tenant: str) -> Principal:
    # These memory-adapter API tests exercise resource scoping with a stubbed
    # principal. Verified OIDC routes must use PostgreSQL and are covered by
    # the disposable-PostgreSQL integration suite.
    return Principal(
        actor_id=actor,
        role="coach",
        tenant_id=tenant,
        resource_owner_id=None,
        verified=False,
        source="development_headers",
        permissions=frozenset({"product"}),
    )


def _setup(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_PERSISTENCE_MODE", "memory")
    monkeypatch.delenv("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", raising=False)
    coach_roster.reset_memory_state()
    coach_assessment_workflow.reset_memory_state()
    coach_problem_workflow._MEMORY.clear()
    coach_problem_workflow._MEMORY_AUDIT.clear()
    coach_diagnostic_workflow.reset_memory_state()
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
    athletes = {
        "coach-a": coach_roster.create_owned_athlete(
            tenant_id="ACADEMY-A", coach_actor_id="auth0|coach-a", display_name="Athlete A"),
        "coach-b": coach_roster.create_owned_athlete(
            tenant_id="ACADEMY-A", coach_actor_id="auth0|coach-b", display_name="Athlete B"),
        "coach-c": coach_roster.create_owned_athlete(
            tenant_id="ACADEMY-B", coach_actor_id="auth0|coach-c", display_name="Athlete C"),
    }
    assessments = {}
    problems = {}
    for key, athlete in athletes.items():
        tenant = "ACADEMY-B" if key == "coach-c" else "ACADEMY-A"
        actor = "auth0|" + key
        assessment = coach_assessment_workflow.create_assessment(
            tenant_id=tenant, coach_actor_id=actor,
            athlete_id=athlete["athlete_id"], template_id="BASELINE-" + key,
            measurements={"entry_quality": 7})
        assessments[key] = assessment
        problems[key] = coach_problem_workflow.create_problem_statement(
            tenant_id=tenant, coach_actor_id=actor,
            athlete_id=athlete["athlete_id"], assessment_id=assessment["assessment_id"],
            statement="Entry timing degrades under resistance.",
            problem_type="technical_execution",
        )
    return client, headers, athletes, assessments, problems


def _evidence(assessment_id, **overrides):
    record = {
        "evidence_id": "EVIDENCE-A",
        "subject_type": "assessment",
        "subject_id": assessment_id,
        "evidence_level": "E3",
        "status": "VERIFIED",
        "source_ref": "assessment://coach-diagnostic-test",
        "claim": "Late entry observed in four attempts.",
        "observed_value": {"count": 4},
        "verified_by": "trusted-test-fixture",
        "verified_at": "2026-11-10T00:00:00Z",
        "notes": None,
    }
    record.update(overrides)
    return record


def test_cause_context_is_bearer_owned_and_audited(monkeypatch):
    client, headers, athletes, assessments, problems = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    problem_id = problems["coach-a"]["problem_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/problem-statements/{problem_id}/cause-context"
    forged = {**headers["coach-a"], "X-KAIZO-Actor": "attacker",
              "X-KAIZO-Role": "administrator", "X-KAIZO-Tenant": "ACADEMY-B"}
    created = client.post(path, headers=forged, json={
        "cause": "Grip acquisition begins after the opponent has stabilized posture.",
        "context": {"phase": "kumi-kata"},
        "contributing_factors": ["distance", "timing"],
        "framed_by": "forged-client",
    })
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["framed_by"] == "auth0|coach-a"
    assert record["assessment_id"] == assessments["coach-a"]["assessment_id"]
    assert record["execution_authorized"] is False
    read = client.get(path, headers=headers["coach-a"])
    assert read.status_code == 200
    assert read.json()["framings"] == [{k: v for k, v in record.items()
                                        if k not in ("coach_final_authority", "execution_authorized")}]
    assert client.get(path, headers=headers["coach-b"]).status_code == 404
    assert client.get(path, headers=headers["coach-c"]).status_code == 404
    assert coach_diagnostic_workflow._MEMORY_AUDIT[0]["who"] == "auth0|coach-a"


def test_diagnosis_requires_verified_same_resource_evidence_and_is_scoped(monkeypatch):
    client, headers, athletes, assessments, problems = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    problem_id = problems["coach-a"]["problem_id"]
    assessment_id = assessments["coach-a"]["assessment_id"]
    evidence = _evidence(assessment_id)
    monkeypatch.setattr(persistence, "get_evidence",
                        lambda evidence_id: evidence if evidence_id == evidence["evidence_id"] else None)
    path = f"/api/v1/product/coach/athletes/{athlete_id}/problem-statements/{problem_id}/diagnoses"
    created = client.post(path, headers=headers["coach-a"], json={
        "evidence_ids": ["EVIDENCE-A"], "diagnosis": "Timing breakdown under resistance.",
        "confidence": "HIGH", "resolution_state": "RESOLVED",
        "diagnosed_by": "forged-client",
    })
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["diagnosed_by"] == "auth0|coach-a"
    assert record["confidence"] == "HIGH"
    assert record["resolution_state"] == "RESOLVED"
    assert record["execution_authorized"] is False
    read = client.get(path, headers=headers["coach-a"])
    assert read.status_code == 200
    assert read.json()["diagnoses"][0]["diagnosis_id"] == record["diagnosis_id"]
    assert client.get(path, headers=headers["coach-b"]).status_code == 404
    assert client.get(path, headers=headers["coach-c"]).status_code == 404
    assert coach_diagnostic_workflow._MEMORY_AUDIT[-1]["action"] == "COACH_EVIDENCE_LINKED_DIAGNOSIS_CREATED"


def test_diagnosis_rejects_missing_unverified_e0_and_cross_resource_evidence(monkeypatch):
    client, headers, athletes, assessments, problems = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    problem_id = problems["coach-a"]["problem_id"]
    assessment_id = assessments["coach-a"]["assessment_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/problem-statements/{problem_id}/diagnoses"
    missing = client.post(path, headers=headers["coach-a"], json={
        "evidence_ids": ["missing"], "diagnosis": "Unsupported"})
    assert missing.status_code == 404
    evidence = _evidence(assessment_id, evidence_level="E0")
    monkeypatch.setattr(persistence, "get_evidence", lambda _: evidence)
    e0 = client.post(path, headers=headers["coach-a"], json={
        "evidence_ids": ["EVIDENCE-A"], "diagnosis": "E0 cannot support diagnosis"})
    assert e0.status_code == 409
    evidence = _evidence(assessment_id, status="PENDING")
    monkeypatch.setattr(persistence, "get_evidence", lambda _: evidence)
    pending = client.post(path, headers=headers["coach-a"], json={
        "evidence_ids": ["EVIDENCE-A"], "diagnosis": "Pending evidence"})
    assert pending.status_code == 409
    evidence = _evidence(assessments["coach-b"]["assessment_id"])
    monkeypatch.setattr(persistence, "get_evidence", lambda _: evidence)
    cross = client.post(path, headers=headers["coach-a"], json={
        "evidence_ids": ["EVIDENCE-A"], "diagnosis": "Cross-athlete evidence"})
    assert cross.status_code == 409


def test_diagnosis_rejects_invalid_confidence_state_and_anonymous_requests(monkeypatch):
    client, headers, athletes, assessments, problems = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    problem_id = problems["coach-a"]["problem_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/problem-statements/{problem_id}/diagnoses"
    assert client.post(path, json={"evidence_ids": ["x"], "diagnosis": "anonymous"}).status_code == 401
    bad_confidence = client.post(path, headers=headers["coach-a"], json={
        "evidence_ids": ["x"], "diagnosis": "Bad confidence", "confidence": "CERTAIN"})
    assert bad_confidence.status_code == 400
    bad_state = client.post(path, headers=headers["coach-a"], json={
        "evidence_ids": ["x"], "diagnosis": "Bad state", "resolution_state": "MAYBE"})
    assert bad_state.status_code == 400
    assert client.post("/api/v1/problem-statements/missing/diagnosis", json={}).status_code in (404, 405, 410)
