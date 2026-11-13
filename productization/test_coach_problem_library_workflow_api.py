from __future__ import annotations

from fastapi.testclient import TestClient

import main
import persistence
from productization import (
    coach_assessment_workflow,
    coach_problem_library_workflow,
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


def _item(item_id="PRB-017-001", **overrides):
    item = {
        "knowledge_id": item_id, "id": item_id, "domain": "problem",
        "title": "Entry timing problem", "source_type": "problem_library",
        "source_ref": "problem-library://entry-timing", "source_version": "1.0",
        "provenance_note": "Approved canonical problem entry with source traceability.",
        "evidence_refs": ["evidence://problem-library/source-001"],
        "evidence_status": "VERIFIED", "lifecycle_status": "APPROVED",
        "changed_by": "knowledge-curator", "updated_at": "2026-11-10T00:00:00Z",
    }
    item.update(overrides)
    return item


def _setup(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_PERSISTENCE_MODE", "memory")
    monkeypatch.delenv("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", raising=False)
    coach_roster.reset_memory_state()
    coach_assessment_workflow.reset_memory_state()
    coach_problem_library_workflow.reset_memory_state()
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
    library = {
        "PRB-017-001": _item(),
        "PRB-017-002": _item("PRB-017-002", lifecycle_status="DRAFT"),
        "PRB-017-003": _item("PRB-017-003", evidence_status="UNVERIFIED"),
        "PRB-017-004": _item("PRB-017-004", source_ref="", provenance_note=""),
        "KPI-001": _item("KPI-001", domain="kpi", source_type="kpi"),
        "PRB-017-005": {
            "id": "PRB-017-005", "domain": "problem", "status": "Published",
            "title": "Legacy published item",
        },
    }
    monkeypatch.setattr(persistence, "load_knowledge", lambda: library)
    client = TestClient(main.app)
    headers = {key: {"Authorization": f"Bearer {key}"} for key in principals}
    athletes, assessments = {}, {}
    for key in principals:
        tenant, actor = ("ACADEMY-B", "auth0|coach-c") if key == "coach-c" else ("ACADEMY-A", "auth0|" + key)
        athletes[key] = coach_roster.create_owned_athlete(
            tenant_id=tenant, coach_actor_id=actor, display_name="Library athlete " + key)
        assessments[key] = coach_assessment_workflow.create_assessment(
            tenant_id=tenant, coach_actor_id=actor, athlete_id=athletes[key]["athlete_id"],
            template_id="LIBRARY-BASELINE-" + key, measurements={"entry_quality": 7})
    return client, headers, athletes, assessments, library


def test_problem_library_lists_only_approved_verified_provenance_bearing_problem_entries(monkeypatch):
    client, headers, athletes, assessments, library = _setup(monkeypatch)
    response = client.get("/api/v1/product/coach/problem-library", headers=headers["coach-a"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["knowledge_id"] == "PRB-017-001"
    assert body["items"][0]["lifecycle_status"] == "APPROVED"
    assert body["items"][0]["evidence_status"] == "VERIFIED"
    assert body["publication_gate"] == "APPROVED_AND_VERIFIED_WITH_PROVENANCE"
    assert body["execution_authorized"] is False
    query = client.get("/api/v1/product/coach/problem-library?query=timing", headers=headers["coach-a"])
    assert query.status_code == 200 and query.json()["total"] == 1
    assert client.get("/api/v1/product/coach/problem-library", params={"limit": 101},
                      headers=headers["coach-a"]).status_code == 400


def test_problem_library_selection_is_bearer_owned_assessment_scoped_and_audited(monkeypatch):
    client, headers, athletes, assessments, library = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    assessment_id = assessments["coach-a"]["assessment_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/assessments/{assessment_id}/problem-library-selections"
    forged = {**headers["coach-a"], "X-KAIZO-Actor": "attacker",
              "X-KAIZO-Role": "administrator", "X-KAIZO-Tenant": "ACADEMY-B"}
    created = client.post(path, headers=forged, json={
        "library_item_id": "PRB-017-001", "selected_by": "forged-client"})
    assert created.status_code == 201, created.text
    record = created.json()
    assert record["selected_by"] == "auth0|coach-a"
    assert record["lifecycle_status"] == "APPROVED"
    assert record["evidence_status"] == "VERIFIED"
    assert record["execution_authorized"] is False
    listed = client.get(path, headers=headers["coach-a"])
    assert listed.status_code == 200 and len(listed.json()["selections"]) == 1
    selection_id = listed.json()["selections"][0]["selection_id"]
    read = client.get(path + "/" + selection_id, headers=headers["coach-a"])
    assert read.status_code == 200 and read.json()["selection_id"] == selection_id
    assert client.get(path, headers=headers["coach-b"]).status_code == 404
    assert client.get(path, headers=headers["coach-c"]).status_code == 404
    assert coach_problem_library_workflow._MEMORY_AUDIT[0]["who"] == "auth0|coach-a"


def test_problem_library_rejects_legacy_unverified_and_cross_athlete_selections(monkeypatch):
    client, headers, athletes, assessments, library = _setup(monkeypatch)
    athlete_id = athletes["coach-a"]["athlete_id"]
    assessment_id = assessments["coach-a"]["assessment_id"]
    path = f"/api/v1/product/coach/athletes/{athlete_id}/assessments/{assessment_id}/problem-library-selections"
    unverified = client.post(path, headers=headers["coach-a"], json={"library_item_id":"PRB-017-003"})
    assert unverified.status_code == 409
    legacy = client.post(path, headers=headers["coach-a"], json={"library_item_id":"PRB-017-005"})
    assert legacy.status_code == 409
    missing = client.post(path, headers=headers["coach-a"], json={"library_item_id":"missing"})
    assert missing.status_code == 404
    wrong_assessment = client.post(
        f"/api/v1/product/coach/athletes/{athlete_id}/assessments/{assessments['coach-b']['assessment_id']}/problem-library-selections",
        headers=headers["coach-a"], json={"library_item_id":"PRB-017-001"})
    assert wrong_assessment.status_code == 404
    assert client.post(path, json={"library_item_id":"PRB-017-001"}).status_code == 401


def test_problem_library_selection_openapi_hides_unscoped_legacy_routes(monkeypatch):
    client, headers, athletes, assessments, library = _setup(monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/product/coach/problem-library" in paths
    assert "/api/v1/product/coach/athletes/{athlete_id}/assessments/{assessment_id}/problem-library-selections" in paths
    assert "/api/v1/problem-library" in paths  # legacy shared read-only listing remains documented
    assert "/api/v1/problem-library/selections" not in paths
    retired = client.post("/api/v1/problem-library/selections", headers=headers["coach-a"], json={
        "athlete_id": athletes["coach-a"]["athlete_id"],
        "assessment_id": assessments["coach-a"]["assessment_id"],
        "library_item_id": "PRB-017-001", "selected_by": "forged-client"})
    assert retired.status_code == 410
