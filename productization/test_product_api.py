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
    from productization import coach_roster
    coach_roster.reset_memory_state()
    athlete = coach_roster.create_owned_athlete(
        tenant_id="T1", coach_actor_id="A1", display_name="Test athlete"
    )
    c = client()
    payload = {
        "resource_tenant_id": "T1",
        "athlete_id": athlete["athlete_id"],
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
    from productization import coach_roster
    coach_roster.reset_memory_state()
    athlete = coach_roster.create_owned_athlete(
        tenant_id="T1", coach_actor_id="A1", display_name="Test athlete"
    )
    c = client()
    payload = {
        "resource_tenant_id": "T2",
        "athlete_id": athlete["athlete_id"],
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

def test_product_decision_requires_owned_athlete_and_rejects_case_only():
    c = client()
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


def test_product_adaptation_requires_owned_decision_cycle():
    from productization import coach_roster, coach_decision_cycles
    coach_roster.reset_memory_state()
    coach_decision_cycles.reset_memory_state()
    athlete = coach_roster.create_owned_athlete(
        tenant_id="T1", coach_actor_id="A1", display_name="Adaptation athlete"
    )
    c = client()
    decision_payload = {
        "athlete_id": athlete["athlete_id"],
        "case_id": "CASE-ADAPT-API", "decision": {"choice": "adapt"},
        "intervention": {"drill": "seoi"}, "response_kpi": {"score": 1},
        "retest": {"score": 1},
    }
    decision = c.post("/api/v1/product/decision", json=decision_payload, headers=headers("coach"))
    assert decision.status_code == 200
    cycle_id = decision.json()["decision_cycle_id"]

    payload = {
        "athlete_id": athlete["athlete_id"],
        "decision_cycle_id": cycle_id, "case_id": "CASE-ADAPT-API",
        "operation": "individual_adaptation", "common_core": {"principle": "retain"},
        "dynamic_inputs": {"readiness": "medium"},
        "individual_change": {"load": "adjust"},
    }
    response = c.post("/api/v1/product/adaptation", json=payload, headers=headers("coach"))
    assert response.status_code == 200
    assert response.json()["status"] == "ADAPTED"
    assert response.json()["decision_cycle_id"] == cycle_id
    assert response.json()["decision_cycle_version"] == 2

    read_back = c.get(
        f"/api/v1/product/coach/athletes/{athlete['athlete_id']}/decision-cycles/{cycle_id}",
        headers=headers("coach"),
    )
    assert read_back.status_code == 200
    assert read_back.json()["adaptation_output"]["status"] == "ADAPTED"
    assert read_back.json()["version"] == 2

    forged = dict(payload, decision_cycle_id="cycle-owned-by-another-coach")
    assert c.post("/api/v1/product/adaptation", json=forged, headers=headers("coach")).status_code == 404
    assert c.get(
        f"/api/v1/product/coach/athletes/{athlete['athlete_id']}/decision-cycles/{cycle_id}",
        headers=headers("coach", actor="A2"),
    ).status_code == 404
    wrong_case = dict(payload, case_id="CASE-FORGED")
    assert c.post("/api/v1/product/adaptation", json=wrong_case, headers=headers("coach")).status_code == 409


def test_legacy_decision_endpoints_are_retired():
    c = client()
    loop = c.post("/api/v1/decision/loop", json={
        "case_id": "CASE-UNSCOPED", "decision": {"x": 1},
        "intervention": {"x": 1}, "response_kpi": {"x": 1}, "retest": {"x": 1},
    })
    adaptation = c.post("/api/v1/decision/adapt", json={
        "case_id": "CASE-UNSCOPED", "operation": "individual_adaptation",
        "common_core": {"x": 1}, "dynamic_inputs": {"x": 1},
    })
    assert loop.status_code == 410
    assert adaptation.status_code == 410


def test_anonymous_decision_request_fails_closed(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    response = client().post("/api/v1/product/decision", json={
        "resource_tenant_id": "T1", "athlete_id": "athlete-1",
        "case_id": "CASE-ANON", "decision": {"x": 1},
        "intervention": {"x": 1}, "response_kpi": {"x": 1}, "retest": {"x": 1},
    })
    assert response.status_code == 401


def test_intervention_also_enforces_verified_coach_athlete_ownership():
    from productization import coach_roster
    coach_roster.reset_memory_state()
    athlete = coach_roster.create_owned_athlete(
        tenant_id="T1", coach_actor_id="A1", display_name="Intervention athlete"
    )
    payload = {
        "resource_tenant_id": "T1",
        "athlete_id": athlete["athlete_id"],
        "case_id": "CASE-INTERVENTION",
        "decision": {"choice": "retain"},
        "intervention": {"drill": "seoi"},
        "response_kpi": {"score": 1},
        "retest": {"score": 1},
        "coach_approved": True,
    }
    denied = client().post(
        "/api/v1/product/intervention", json=payload,
        headers=headers("coach", actor="A2"),
    )
    assert denied.status_code == 404

    allowed = client().post(
        "/api/v1/product/intervention", json=payload,
        headers=headers("coach", actor="A1"),
    )
    assert allowed.status_code == 200
    assert allowed.json()["athlete_id"] == athlete["athlete_id"]
