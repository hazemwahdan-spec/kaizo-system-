"""Keep the legacy audit-log endpoint fail-closed until tenant scoping is real."""
from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def test_legacy_audit_logs_endpoint_stays_closed_without_identity():
    response = client.get("/api/v1/audit/logs")

    assert response.status_code == 503
    assert "tenant authorization" in response.json()["detail"].lower()
    assert "logs" not in response.json()


def test_legacy_audit_logs_endpoint_stays_closed_for_unverified_bearer():
    response = client.get(
        "/api/v1/audit/logs",
        headers={"Authorization": "Bearer deliberately-invalid-token"},
    )

    # The route is a containment boundary, not an authorization implementation.
    # It must not reveal audit records to any caller until tenant-scoped durable
    # storage and role/tenant authorization are implemented and verified.
    assert response.status_code == 503
    assert "tenant authorization" in response.json()["detail"].lower()
    assert "timestamp" not in response.text
    assert "who" not in response.text
