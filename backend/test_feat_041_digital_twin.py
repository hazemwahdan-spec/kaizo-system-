"""Regression: legacy unscoped Digital Twin routes must fail closed."""
from fastapi.testclient import TestClient
from main import app

client=TestClient(app)


def test_legacy_unscoped_digital_twin_sync_is_retired():
    response=client.post("/api/v1/digital-twin/sync",json={
        "case_id":"CASE-LEGACY","entity_id":"ATHLETE-LEGACY",
        "state":{"readiness":"test"},"source_event":"LEGACY_TEST",
        "coach_final_authority":True,
    })
    assert response.status_code==410


def test_legacy_unscoped_digital_twin_read_is_retired():
    assert client.get("/api/v1/digital-twin/ATHLETE-LEGACY").status_code==410
