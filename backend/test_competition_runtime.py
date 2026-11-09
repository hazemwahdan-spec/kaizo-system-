"""Fail-closed tests for unscoped FEAT-066..070 competition routes."""
import os
os.environ["KAIZO_IDENTITY_MODE"] = "production"
os.environ.pop("KAIZO_ALLOW_UNSCOPED_LEGACY_ROUTES_FOR_TESTS", None)

from fastapi.testclient import TestClient
import main
import competition_runtime

client = TestClient(main.app, raise_server_exceptions=False)
FORGED_HEADERS = {
    "X-KAIZO-Actor": "forged-coach",
    "X-KAIZO-Role": "coach",
    "X-KAIZO-Tenant": "forged-tenant",
    "X-KAIZO-Resource-Owner": "forged-athlete",
}


def test_competition_routes_fail_closed_without_verified_athlete_scope():
    for mapping in (
        competition_runtime.EVENTS, competition_runtime.READINESS,
        competition_runtime.PERFORMANCES, competition_runtime.DECISIONS,
    ):
        mapping.clear()
    cases = [
        ("POST", "/api/v1/competition/events", {"event_name": "Forged", "date": "2026-11-09", "context": {"athlete_id": "forged-athlete"}, "created_by": "forged-coach", "coach_final_authority": True}),
        ("GET", "/api/v1/competition/events/forged-event", None),
        ("POST", "/api/v1/competition/readiness", {"athlete_id": "forged-athlete", "event_id": "forged-event", "indicators": {"ready": True}, "assessed_by": "forged-coach", "coach_final_authority": True}),
        ("GET", "/api/v1/competition/readiness/forged-athlete/forged-event", None),
        ("POST", "/api/v1/competition/performance", {"athlete_id": "forged-athlete", "event_id": "forged-event", "performance": {"score": 1}, "recorded_by": "forged-coach", "coach_final_authority": True}),
        ("GET", "/api/v1/competition/trend/forged-athlete", None),
        ("POST", "/api/v1/competition/next-decision", {"athlete_id": "forged-athlete", "event_id": "forged-event", "decision_basis": {"basis": "forged"}, "decision": {"choice": "forged"}, "decided_by": "forged-coach", "coach_final_authority": True}),
    ]
    for method, path, payload in cases:
        kwargs = {"headers": FORGED_HEADERS}
        if payload is not None:
            kwargs["json"] = payload
        response = client.request(method, path, **kwargs)
        assert response.status_code == 410, (method, path, response.status_code, response.text)
    assert not any((competition_runtime.EVENTS, competition_runtime.READINESS,
                    competition_runtime.PERFORMANCES, competition_runtime.DECISIONS))
