import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app


def client():
    return TestClient(app)


def headers(role, tenant="T1", actor="A1", owner=None):
    h = {"X-KAIZO-Actor": actor, "X-KAIZO-Role": role, "X-KAIZO-Tenant": tenant}
    if owner:
        h["X-KAIZO-Resource-Owner"] = owner
    return h


def test_product_navigation_api_exposes_all_roles():
    c = client()
    for role in ("academy", "coach", "athlete", "parent"):
        r = c.get("/api/v1/product/navigation", headers=headers(role, owner="athlete-1"))
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == role
        assert body["execution_authorized"] is False
        assert body["coach_final_authority"] is True


def test_product_decision_api_is_coach_only():
    c = client()
    payload = {
        "resource_tenant_id": "T1",
        "case_id": "CASE-API-1",
        "decision": {"choice": "adapt"},
        "intervention": {"drill": "seoi"},
        "response_kpi": {"score": 1},
        "retest": {"score": 1},
    }
    ok = c.post("/api/v1/product/decision", json=payload, headers=headers("coach"))
    assert ok.status_code == 200
    assert ok.json()["coach_final_authority"] is True

    denied = c.post("/api/v1/product/decision", json=payload, headers=headers("athlete", owner="athlete-1"))
    assert denied.status_code == 403


def test_product_api_denies_cross_tenant():
    c = client()
    payload = {
        "resource_tenant_id": "T2",
        "case_id": "CASE-API-2",
        "decision": {"choice": "adapt"},
        "intervention": {"drill": "seoi"},
        "response_kpi": {"score": 1},
        "retest": {"score": 1},
    }
    r = c.post("/api/v1/product/decision", json=payload, headers=headers("coach", tenant="T1"))
    assert r.status_code == 403


def test_parent_api_requires_explicit_link():
    c = client()
    r = c.get(
        "/api/v1/product/parents/linked/athlete-2/progress",
        params={"resource_tenant_id": "T1"},
        headers=headers("parent", owner="athlete-1"),
    )
    assert r.status_code == 403


def test_product_api_fails_closed_without_production_identity(monkeypatch):
    monkeypatch.delenv("KAIZO_IDENTITY_MODE", raising=False)
    response = client().get(
        "/api/v1/product/navigation",
        headers={
            "X-KAIZO-Actor": "coach-1",
            "X-KAIZO-Role": "coach",
            "X-KAIZO-Tenant": "academy-a",
        },
    )
    assert response.status_code == 503


def test_parent_progress_forwards_authorization_header_to_identity_context(monkeypatch):
    # This isolates route wiring: the real identity resolver is tested elsewhere.
    # The assertion prevents the handler from silently dropping the bearer token.
    from productization import product_api

    observed = {}

    def fake_ctx(actor_id, role, tenant_id, owner, authorization=None):
        observed["authorization"] = authorization
        return object()

    class FakeSurface:
        def parent_progress(self, context, resource_tenant_id, athlete_id, extra):
            return {"ok": True}

    monkeypatch.setattr(product_api, "ctx", fake_ctx)
    monkeypatch.setattr(product_api, "get_surface", lambda: FakeSurface())

    response = client().get(
        "/api/v1/product/parents/linked/athlete-2/progress",
        params={"resource_tenant_id": "T1"},
        headers={
            **headers("parent", owner="athlete-2"),
            "Authorization": "Bearer regression-token",
        },
    )

    assert response.status_code == 200
    assert observed["authorization"] == "Bearer regression-token"
