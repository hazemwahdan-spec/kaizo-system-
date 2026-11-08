"""API-level positive and negative authorization regression tests.

These tests run only against the local TestClient with explicitly unverified
development identity headers. They do not call production or use real tokens.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app


def client():
    return TestClient(app)


def headers(role="coach", tenant="TENANT-A", actor="test-actor", owner=None):
    value = {
        "X-KAIZO-Actor": actor,
        "X-KAIZO-Role": role,
        "X-KAIZO-Tenant": tenant,
    }
    if owner is not None:
        value["X-KAIZO-Resource-Owner"] = owner
    return value



def create_owned_athlete(actor="test-actor", tenant="TENANT-A"):
    from productization import coach_roster
    coach_roster.reset_memory_state()
    return coach_roster.create_owned_athlete(
        tenant_id=tenant, coach_actor_id=actor, display_name="Security regression athlete"
    )["athlete_id"]


def decision_payload(resource_tenant_id="TENANT-A", athlete_id="athlete-A"):
    return {
        "resource_tenant_id": resource_tenant_id,
        "athlete_id": athlete_id,
        "case_id": "SECURITY-REGRESSION-CASE",
        "decision": {"choice": "adapt"},
        "intervention": {"drill": "controlled-test"},
        "response_kpi": {"score": 1},
        "retest": {"score": 2},
    }


def test_missing_identity_headers_and_bearer_fail_closed():
    response = client().get("/api/v1/product/navigation")
    # The active test environment may be development or production; both
    # must deny the request when no identity headers or bearer are supplied.
    assert response.status_code == 503


def test_unknown_role_is_rejected_closed(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    response = client().get(
        "/api/v1/product/navigation",
        headers=headers(role="administrator"),
    )
    assert response.status_code == 503


def test_athlete_cannot_read_another_athletes_progress():
    response = client().get(
        "/api/v1/product/athletes/athlete-B/progress",
        params={"resource_tenant_id": "TENANT-A"},
        headers=headers(role="athlete", owner="athlete-A"),
    )
    assert response.status_code == 403


def test_athlete_progress_rejects_cross_tenant_resource():
    response = client().get(
        "/api/v1/product/athletes/athlete-A/progress",
        params={"resource_tenant_id": "TENANT-B"},
        headers=headers(role="athlete", owner="athlete-A"),
    )
    assert response.status_code == 403


def test_intervention_requires_coach_role_and_explicit_approval():
    c = client()
    athlete_id = create_owned_athlete()
    unapproved = {**decision_payload(athlete_id=athlete_id), "coach_approved": False}
    denied = c.post(
        "/api/v1/product/intervention",
        json=unapproved,
        headers=headers(role="coach", owner="athlete-A"),
    )
    assert denied.status_code == 403

    non_coach = {**decision_payload(athlete_id=athlete_id), "coach_approved": True}
    role_denied = c.post(
        "/api/v1/product/intervention",
        json=non_coach,
        headers=headers(role="athlete", owner="athlete-A"),
    )
    assert role_denied.status_code == 403


def test_intervention_with_coach_approval_stays_non_executing():
    athlete_id = create_owned_athlete()
    response = client().post(
        "/api/v1/product/intervention",
        json={**decision_payload(athlete_id=athlete_id), "coach_approved": True},
        headers=headers(role="coach", owner="athlete-A"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_authorized"] is False
    assert body["coach_final_authority"] is True


def test_oidc_verify_rejects_missing_bearer():
    response = client().get("/api/v1/product/auth/oidc/verify")
    assert response.status_code == 401



def test_decision_api_uses_verified_bearer_claims_not_spoofed_identity_headers(monkeypatch):
    from productization import product_api, coach_roster
    from productization.identity import Principal
    import main

    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    coach_roster.reset_memory_state()
    athlete_id = coach_roster.create_owned_athlete(
        tenant_id="TENANT-A", coach_actor_id="trusted-coach",
        display_name="OIDC scoped decision athlete",
    )["athlete_id"]
    trusted = Principal(
        actor_id="trusted-coach", role="coach", tenant_id="TENANT-A",
        resource_owner_id=None, verified=True, source="oidc_jwt",
    )
    def resolve(_authorization):
        assert _authorization == "Bearer verified-test-token"
        return trusted

    monkeypatch.setattr(product_api, "resolve_bearer_principal", resolve)
    monkeypatch.setattr(main, "resolve_bearer_principal", resolve)
    response = client().post(
        "/api/v1/product/decision",
        json=decision_payload(athlete_id=athlete_id),
        headers={
            "Authorization": "Bearer verified-test-token",
            "X-KAIZO-Actor": "spoofed-actor",
            "X-KAIZO-Role": "athlete",
            "X-KAIZO-Tenant": "TENANT-SPOOFED",
            "X-KAIZO-Resource-Owner": "other-athlete",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["recorded_by"] == "trusted-coach"
