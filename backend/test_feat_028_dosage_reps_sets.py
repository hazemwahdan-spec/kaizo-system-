"""FEAT-028 legacy dosage endpoints remain fail-closed pending a scoped replacement.

This is a security acceptance test, not evidence that dosage authoring is complete.
The legacy endpoints accept caller-supplied athlete/coach IDs and are intentionally
retired. Do not restore them to make this test pass.
"""
from fastapi.testclient import TestClient

from backend.main import app


def test_feat_028_legacy_dosage_routes_fail_closed():
    client = TestClient(app)

    cases = [
        ("POST", "/api/v1/training-plans", {
            "athlete_id": "ATH-028-FORGED",
            "title": "Unscoped plan",
            "created_by": "forged-coach",
        }),
        ("POST", "/api/v1/training-plans/PLAN-028/sessions", {
            "plan_id": "PLAN-028",
            "athlete_id": "ATH-028-FORGED",
            "title": "Unscoped session",
            "duration_minutes": 60,
            "blocks": [{"name": "Technical", "duration_minutes": 60}],
            "created_by": "forged-coach",
        }),
        ("POST", "/api/v1/training-sessions/SESSION-028/dosage", {
            "session_id": "SESSION-028",
            "block_name": "Technical",
            "sets": 4,
            "reps": 8,
            "prescribed_by": "forged-coach",
        }),
        ("GET", "/api/v1/training-dosages/DOSAGE-028", None),
        ("GET", "/api/v1/training-sessions/SESSION-028/dosage", None),
    ]

    for method, path, payload in cases:
        kwargs = {"headers": {
            "X-KAIZO-Actor": "forged-coach",
            "X-KAIZO-Role": "coach",
            "X-KAIZO-Tenant": "forged-tenant",
        }}
        if payload is not None:
            kwargs["json"] = payload
        response = client.request(method, path, **kwargs)
        assert response.status_code == 410, (method, path, response.status_code, response.text)
        assert "legacy Core API retired" in response.json()["detail"]
