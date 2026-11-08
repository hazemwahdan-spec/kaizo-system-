"""Regression tests for legacy Core routes that bypass Coach ownership."""

import os

# Exercise the production default even though the persistence workflow enables
# an explicit test-only compatibility switch for older domain acceptance tests.
os.environ["KAIZO_IDENTITY_MODE"] = "production"
os.environ.pop("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", None)

import pytest
from fastapi.testclient import TestClient

import main


client = TestClient(main.app)
FORGED_HEADERS = {
    "X-KAIZO-Actor": "forged-coach",
    "X-KAIZO-Role": "coach",
    "X-KAIZO-Tenant": "forged-tenant",
    "X-KAIZO-Resource-Owner": "forged-athlete",
}
FORGED_BODY = {
    "athlete_id": "forged-athlete",
    "actor_id": "forged-coach",
    "created_by": "forged-coach",
    "recorded_by": "forged-coach",
    "coach_id": "forged-coach",
    "coach_final_authority": True,
    "execution_authorized": False,
}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/athletes"),
        ("GET", "/api/v1/athletes/legacy-athlete"),
        ("POST", "/api/v1/assessments"),
        ("GET", "/api/v1/assessments/legacy-assessment"),
        ("POST", "/api/v1/problem-statements"),
        ("GET", "/api/v1/problem-statements"),
        ("POST", "/api/v1/diagnoses/legacy-diagnosis/decision-candidates"),
        ("GET", "/api/v1/diagnoses/legacy-diagnosis/decision-candidates"),
        ("POST", "/api/v1/decision-candidates/legacy-candidate/coach-review"),
        ("GET", "/api/v1/decision-candidates/legacy-candidate/decision-record"),
        ("POST", "/api/v1/training-plans"),
        ("GET", "/api/v1/training-sessions/legacy-session"),
        ("POST", "/api/v1/training-sessions/legacy-session/dosage"),
        ("GET", "/api/v1/training-dosages/legacy-dosage"),
        ("POST", "/api/v1/problem-library/selections"),
        ("GET", "/api/v1/problem-library/selections/legacy-selection"),
        ("POST", "/api/v1/kpis/captures"),
        ("GET", "/api/v1/kpis/legacy-kpi"),
        ("POST", "/api/v1/state-snapshots"),
        ("GET", "/api/v1/state-snapshots"),
        ("GET", "/api/v1/state-snapshots/legacy-snapshot"),
        ("POST", "/api/v1/digital-twin/sync"),
        ("GET", "/api/v1/digital-twin/legacy-athlete"),
        ("POST", "/api/v1/decision/loop"),
        ("POST", "/api/v1/decision/adapt"),
        ("POST", "/api/v1/rules/evaluate"),
        ("POST", "/api/v1/safety/evaluate"),
        ("POST", "/api/v1/knowledge/ingest"),
    ],
)
def test_unscoped_legacy_core_routes_fail_closed(method: str, path: str):
    kwargs = {"headers": FORGED_HEADERS}
    if method == "POST":
        kwargs["json"] = FORGED_BODY
    response = client.request(method, path, **kwargs)
    assert response.status_code == 410, (method, path, response.status_code, response.text)
    assert "legacy Core API retired" in response.json()["detail"]


def test_development_mode_alone_does_not_enable_legacy_route_bypass(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    monkeypatch.delenv("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", raising=False)
    response = client.get("/api/v1/athletes/legacy-athlete", headers=FORGED_HEADERS)
    assert response.status_code == 410, response.text


def test_openapi_hides_retired_routes_and_keeps_protected_replacements():
    paths = main.app.openapi()["paths"]
    assert not any(main._is_legacy_unscoped_coach_route(path) for path in paths)
    assert "/api/v1/health" in paths
    assert "/api/v1/problem-library" in paths
    assert "/api/v1/product/coach/athletes" in paths
    assert "/api/v1/training-workflow/feat-037/retest" in paths
    assert "/api/v1/state-cycle/feat-042/digital-twin-state" in paths
