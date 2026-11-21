from __future__ import annotations

from fastapi.testclient import TestClient

import main
import persistence
from productization import coach_assessment_workflow, coach_problem_workflow, coach_roster, product_api
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
    for key, athlete in athletes.items():
        assessments[key] = coach_assessment_workflow.create_assessment(
            tenant_id="ACADEMY-B" if key == "coach-c" else "ACADEMY-A",
            coach_actor_id="auth0|" + key, athlete_id=athlete["athlete_id"],
            template_id="BASELINE-" + key, measurements={"entry_quality": 7})
    return client, headers, athletes, assessments


def test_problem_statement_is_bearer_owned_and_cross_scope_denied(monkeypatch):
    client, headers, athletes, assessments = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    assessment_id = assessments["coach-a"]["assessment_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/problem-statements"
    forged = {**headers["coach-a"], "X-KAIZO-Actor": "attacker",
              "X-KAIZO-Role": "administrator", "X-KAIZO-Tenant": "ACADEMY-B"}
    created = client.post(path, headers=forged, json={
        "assessment_id": assessment_id,
        "statement": "Entry quality drops under live resistance.",
        "problem_type": "technical_execution",
        "impact": "Reduced successful entry rate.",
        "context": {"phase": "tsukuri"},
        "structured_fields": {"observable": "late_entry"},
        "created_by": "forged-client",
    })
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["created_by"] == "auth0|coach-a"
    assert record["athlete_id"] == athlete_id
    assert record["coach_final_authority"] is True
    assert record["execution_authorized"] is False

    read = client.get(path + "/" + record["problem_id"], headers=headers["coach-a"])
    assert read.status_code == 200
    assert read.json()["statement"] == record["statement"]
    assert client.get(path + "/" + record["problem_id"], headers=headers["coach-b"]).status_code == 404
    assert client.get(path + "/" + record["problem_id"], headers=headers["coach-c"]).status_code == 404
    path_b = f"/api/v1/product/coach/athletes/{athletes['coach-b']['athlete_id']}/problem-statements"
    path_c = f"/api/v1/product/coach/athletes/{athletes['coach-c']['athlete_id']}/problem-statements"
    assert client.get(path_b, headers=headers["coach-b"]).status_code == 200
    assert client.get(path_b, headers=headers["coach-b"]).json()["total"] == 0
    assert client.get(path_c, headers=headers["coach-c"]).status_code == 200
    assert client.get(path_c, headers=headers["coach-c"]).json()["total"] == 0
    assert coach_problem_workflow._MEMORY_AUDIT[0]["who"] == "auth0|coach-a"
    assert coach_problem_workflow._MEMORY_AUDIT[0]["tenant_id"] == "ACADEMY-A"


def test_problem_statement_requires_assessment_from_same_owned_athlete(monkeypatch):
    client, headers, athletes, assessments = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/problem-statements"
    mismatch = client.post(path, headers=headers["coach-a"], json={
        "assessment_id": assessments["coach-b"]["assessment_id"],
        "statement": "Cross athlete reference", "problem_type": "technical_execution"})
    assert mismatch.status_code == 404
    missing = client.post(path, headers=headers["coach-a"], json={
        "assessment_id": "missing", "statement": "No assessment", "problem_type": "technical"})
    assert missing.status_code == 404
    invalid = client.post(path, headers=headers["coach-a"], json={
        "assessment_id": assessments["coach-a"]["assessment_id"],
        "statement": " ", "problem_type": "technical"})
    assert invalid.status_code == 400


def test_problem_statement_requires_bearer_and_hides_retired_unscoped_route(monkeypatch):
    client, headers, athletes, assessments = _setup(monkeypatch)
    path = f"/api/v1/product/coach/athletes/{athletes['coach-a']['athlete_id']}/problem-statements"
    assert client.post(path, json={
        "assessment_id": assessments["coach-a"]["assessment_id"],
        "statement": "Anonymous", "problem_type": "technical"}).status_code == 401
    assert client.post("/api/v1/problem-statements", json={}).status_code in (404, 405, 410)
    openapi = client.get("/openapi.json").json()["paths"]
    assert path in openapi or "/api/v1/product/coach/athletes/{athlete_id}/problem-statements" in openapi
    assert "/api/v1/problem-statements" not in openapi
