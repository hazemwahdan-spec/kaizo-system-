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


def owned_athlete_id():
    from productization import coach_roster

    coach_roster.reset_memory_state()
    athlete = coach_roster.create_owned_athlete(
        tenant_id="TENANT-A",
        coach_actor_id="test-actor",
        display_name="Security regression athlete",
    )
    return athlete["athlete_id"]


def decision_payload(resource_tenant_id="TENANT-A", athlete_id=None):
    payload = {
        "resource_tenant_id": resource_tenant_id,
        "case_id": "SECURITY-REGRESSION-CASE",
        "decision": {"choice": "adapt"},
        "intervention": {"drill": "controlled-test"},
        "response_kpi": {"score": 1},
        "retest": {"score": 2},
    }
    if athlete_id is not None:
        payload["athlete_id"] = athlete_id
    return payload


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
    athlete_id = owned_athlete_id()
    unapproved = {
        **decision_payload(athlete_id=athlete_id),
        "coach_approved": False,
    }
    denied = c.post(
        "/api/v1/product/intervention",
        json=unapproved,
        headers=headers(role="coach", owner=athlete_id),
    )
    assert denied.status_code == 403

    non_coach = {
        **decision_payload(athlete_id=athlete_id),
        "coach_approved": True,
    }
    role_denied = c.post(
        "/api/v1/product/intervention",
        json=non_coach,
        headers=headers(role="athlete", owner=athlete_id),
    )
    assert role_denied.status_code == 403


def test_intervention_with_coach_approval_stays_non_executing():
    athlete_id = owned_athlete_id()
    response = client().post(
        "/api/v1/product/intervention",
        json={
            **decision_payload(athlete_id=athlete_id),
            "coach_approved": True,
        },
        headers=headers(role="coach", owner=athlete_id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["execution_authorized"] is False
    assert body["coach_final_authority"] is True


def test_oidc_verify_rejects_missing_bearer():
    response = client().get("/api/v1/product/auth/oidc/verify")
    assert response.status_code == 401
