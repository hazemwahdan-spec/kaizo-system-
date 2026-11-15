"""Product API contract and authorization tests for Coach-scoped evidence features."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import main
import persistence
from productization import coach_scoped_evidence_api as api
from productization import coach_scoped_evidence_runtime as service

client = TestClient(main.app)


def principal(role="coach", permissions=frozenset({"product"})):
    return SimpleNamespace(
        actor_id="auth0|coach-A", role=role, tenant_id="tenant-A",
        resource_owner_id=None, verified=True, source="oidc_jwt",
        permissions=permissions,
    )


def setup_function():
    os.environ["KAIZO_IDENTITY_MODE"] = "oidc"


def test_all_required_coach_evidence_routes_are_in_openapi():
    paths = main.app.openapi()["paths"]
    expected = {
        "/api/v1/product/coach/athletes/{athlete_id}/knowledge": {"get", "post"},
        "/api/v1/product/coach/athletes/{athlete_id}/knowledge/{knowledge_id}/lifecycle": {"patch"},
        "/api/v1/product/coach/athletes/{athlete_id}/training-sessions/{session_id}/knowledge-links": {"post"},
        "/api/v1/product/coach/athletes/{athlete_id}/actor-traces": {"get", "post"},
        "/api/v1/product/coach/athletes/{athlete_id}/governance": {"put"},
        "/api/v1/product/coach/athletes/{athlete_id}/governance/{resource_type}/{resource_id}": {"get"},
    }
    for path, methods in expected.items():
        assert path in paths
        assert methods.issubset({m.lower() for m in paths[path]})


def test_anonymous_and_invalid_oidc_requests_fail_closed(monkeypatch):
    monkeypatch.setattr(api, "resolve_bearer_principal", lambda token: (_ for _ in ()).throw(
        api.IdentityNotConfiguredError("invalid token")
    ))
    response = client.get("/api/v1/product/coach/athletes/ATH-1/knowledge?query=grip")
    assert response.status_code == 401
    response = client.get("/api/v1/product/coach/athletes/ATH-1/knowledge?query=grip",
                          headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401


def test_noncoach_and_missing_product_permission_are_rejected(monkeypatch):
    monkeypatch.setattr(api, "resolve_bearer_principal", lambda token: principal(role="athlete"))
    response = client.get("/api/v1/product/coach/athletes/ATH-1/knowledge?query=grip",
                          headers={"Authorization": "Bearer signed"})
    assert response.status_code == 403
    monkeypatch.setattr(api, "resolve_bearer_principal", lambda token: principal(permissions=frozenset()))
    response = client.get("/api/v1/product/coach/athletes/ATH-1/knowledge?query=grip",
                          headers={"Authorization": "Bearer signed"})
    assert response.status_code == 403


def test_actor_and_tenant_headers_cannot_override_verified_principal(monkeypatch):
    monkeypatch.setattr(api, "resolve_bearer_principal", lambda token: principal())
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    observed = {}
    def fake_retrieve(**kwargs):
        observed.update(kwargs)
        return []
    monkeypatch.setattr(service, "retrieve_knowledge", fake_retrieve)
    response = client.get(
        "/api/v1/product/coach/athletes/ATH-1/knowledge?query=grip",
        headers={"Authorization": "Bearer signed", "X-KAIZO-Actor": "attacker",
                 "X-KAIZO-Tenant": "tenant-evil", "X-KAIZO-Role": "admin"},
    )
    assert response.status_code == 200
    assert observed["principal"].actor_id == "auth0|coach-A"
    assert observed["principal"].tenant_id == "tenant-A"
    assert observed["athlete_id"] == "ATH-1"


def test_provenance_and_governance_writes_use_service_atomic_boundary(monkeypatch):
    monkeypatch.setattr(api, "resolve_bearer_principal", lambda token: principal())
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    seen = {}
    def fake_provenance(**kwargs):
        seen["provenance"] = kwargs
        return {"knowledge_id": kwargs["knowledge_id"], "lifecycle_status": "DRAFT",
                "evidence_status": "VERIFIED", "version": 1}
    monkeypatch.setattr(service, "record_provenance", fake_provenance)
    response = client.post(
        "/api/v1/product/coach/athletes/ATH-1/knowledge",
        headers={"Authorization": "Bearer signed"},
        json={"knowledge_id":"K-1","source_type":"ASSESSMENT","source_ref":"A-1",
              "source_version":"1","provenance_note":"verified baseline",
              "evidence_refs":["E-1"],"tenant_id":"forged","coach_actor_id":"forged"},
    )
    assert response.status_code == 201
    assert seen["provenance"]["principal"].actor_id == "auth0|coach-A"
    assert "tenant_id" not in seen["provenance"]
    assert "coach_actor_id" not in seen["provenance"]

    def fake_governance(**kwargs):
        seen["governance"] = kwargs
        return {"version": 1, "governance_status": kwargs["governance_status"]}
    monkeypatch.setattr(service, "set_governance", fake_governance)
    response = client.put(
        "/api/v1/product/coach/athletes/ATH-1/governance",
        headers={"Authorization": "Bearer signed"},
        json={"resource_type":"KNOWLEDGE","resource_id":"K-1",
              "governance_status":"REVIEWED","metadata":{},"expected_version":None,
              "tenant_id":"forged","coach_actor_id":"forged"},
    )
    assert response.status_code == 200
    assert seen["governance"]["principal"].tenant_id == "tenant-A"
    assert "tenant_id" not in seen["governance"]
    assert "coach_actor_id" not in seen["governance"]


def test_verified_api_refuses_memory_only_persistence(monkeypatch):
    monkeypatch.setattr(api, "resolve_bearer_principal", lambda token: principal())
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: False)
    response = client.get("/api/v1/product/coach/athletes/ATH-1/knowledge?query=grip",
                          headers={"Authorization": "Bearer signed"})
    assert response.status_code == 503
