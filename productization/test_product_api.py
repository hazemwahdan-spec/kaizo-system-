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



def create_owned_athlete():
    from productization import coach_roster
    coach_roster.reset_memory_state()
    return coach_roster.create_owned_athlete(
        tenant_id="T1", coach_actor_id="A1", display_name="Product API test athlete"
    )["athlete_id"]


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
    athlete_id = create_owned_athlete()
    payload = {
        "resource_tenant_id": "T1",
        "athlete_id": athlete_id,
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
    athlete_id = create_owned_athlete()
    payload = {
        "resource_tenant_id": "T2",
        "athlete_id": athlete_id,
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



def test_product_decision_requires_owned_athlete_and_rejects_case_only_or_cross_coach():
    c = client()
    athlete_id = create_owned_athlete()
    payload = {
        "resource_tenant_id": "T1",
        "case_id": "CASE-ONLY",
        "decision": {"choice": "adapt"},
        "intervention": {"drill": "seoi"},
        "response_kpi": {"score": 1},
        "retest": {"score": 1},
    }
    response = c.post("/api/v1/product/decision", json=payload, headers=headers("coach"))
    assert response.status_code == 422

    payload["athlete_id"] = "not-owned-by-this-coach"
    response = c.post("/api/v1/product/decision", json=payload, headers=headers("coach"))
    assert response.status_code == 404

    from productization import coach_roster
    coach_roster.reset_memory_state()
    coach_roster.create_owned_athlete(
        tenant_id="T1", coach_actor_id="A1", display_name="Current Coach athlete"
    )
    other_athlete = coach_roster.create_owned_athlete(
        tenant_id="T1", coach_actor_id="A2", display_name="Other Coach athlete"
    )["athlete_id"]
    payload["athlete_id"] = other_athlete
    payload["case_id"] = "CASE-ONLY"
    response = c.post("/api/v1/product/decision", json=payload, headers=headers("coach"))
    assert response.status_code == 404


def test_product_adaptation_requires_owned_athlete_and_existing_decision():
    from productization import coach_roster
    coach_roster.reset_memory_state()
    athlete = coach_roster.create_owned_athlete(
        tenant_id="T1", coach_actor_id="A1", display_name="Adaptation athlete"
    )
    import main
    main.DECISION_RECORDS["decision-owned-1"] = {
        "decision_id": "decision-owned-1", "athlete_id": athlete["athlete_id"]
    }
    payload = {
        "resource_tenant_id": "T1",
        "athlete_id": athlete["athlete_id"],
        "decision_id": "decision-owned-1",
        "case_id": "CASE-ADAPT-API",
        "operation": "individual_adaptation",
        "common_core": {"principle": "retain"},
        "dynamic_inputs": {"readiness": "medium"},
        "individual_change": {"load": "adjust"},
    }
    response = client().post("/api/v1/product/adaptation", json=payload, headers=headers("coach"))
    assert response.status_code == 200
    assert response.json()["status"] == "ADAPTED"
    assert response.json()["decision_id"] == "decision-owned-1"
    assert response.json()["recorded_by"] == "A1"

    payload["decision_id"] = "decision-owned-by-another-coach"
    response = client().post("/api/v1/product/adaptation", json=payload, headers=headers("coach"))
    assert response.status_code == 404

    payload["athlete_id"] = "another-coachs-athlete"
    payload["decision_id"] = "decision-owned-1"
    response = client().post("/api/v1/product/adaptation", json=payload, headers=headers("coach"))
    assert response.status_code == 404
