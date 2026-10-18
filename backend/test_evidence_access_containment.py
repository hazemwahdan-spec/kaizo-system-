"""Regression tests for the temporary fail-closed evidence access containment."""
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_evidence_list_is_temporarily_disabled_without_verified_authorization():
    response = client.get("/api/v1/evidence")
    assert response.status_code == 503


def test_evidence_detail_is_temporarily_disabled_without_verified_authorization():
    response = client.get("/api/v1/evidence/containment-probe")
    assert response.status_code == 503


def test_evidence_write_is_temporarily_disabled_without_verified_authorization():
    response = client.post(
        "/api/v1/evidence",
        json={
            "evidence_id": "containment-probe",
            "subject_type": "athlete",
            "subject_id": "athlete-probe",
            "evidence_level": "E1",
            "status": "UNVERIFIED",
            "claim": "containment regression probe",
            "verified_by": "caller-supplied-value",
        },
    )
    assert response.status_code == 503
