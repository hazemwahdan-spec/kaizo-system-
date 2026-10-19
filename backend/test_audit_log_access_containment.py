"""Regression tests for the tenant-scoped audit endpoint."""
from fastapi.testclient import TestClient
import pytest

import main
from audit_authorization import require_tenant_audit_reader
from productization.identity import Principal

client = TestClient(main.app)


def test_audit_endpoint_rejects_anonymous_and_invalid_bearer():
    assert client.get("/api/v1/audit/logs").status_code == 401
    response = client.get("/api/v1/audit/logs", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    assert "logs" not in response.json()


def test_audit_endpoint_requires_durable_postgres(monkeypatch):
    principal = Principal("academy-1", "academy", "tenant-a", None, True, "oidc_jwt")
    main.app.dependency_overrides[require_tenant_audit_reader] = lambda: principal
    monkeypatch.setattr(main.persistence, "is_postgres_enabled", lambda: False)
    try:
        response = client.get("/api/v1/audit/logs")
        assert response.status_code == 503
        assert "Durable tenant-scoped" in response.json()["detail"]
    finally:
        main.app.dependency_overrides.clear()


def test_audit_endpoint_reads_only_verified_principal_tenant(monkeypatch):
    principal = Principal("academy-1", "academy", "tenant-a", None, True, "oidc_jwt")
    main.app.dependency_overrides[require_tenant_audit_reader] = lambda: principal
    monkeypatch.setattr(main.persistence, "is_postgres_enabled", lambda: True)
    calls = []
    monkeypatch.setattr(main.persistence, "list_tenant_audit_logs",
                        lambda *, tenant_id: calls.append(tenant_id) or [
                            {"tenant_id": tenant_id, "action": "SCOPED_EVENT"}])
    try:
        response = client.get("/api/v1/audit/logs?tenant_id=tenant-b")
        assert response.status_code == 200
        assert calls == ["tenant-a"]
        assert response.json()["tenant_id"] == "tenant-a"
        assert response.json()["logs"][0]["tenant_id"] == "tenant-a"
    finally:
        main.app.dependency_overrides.clear()
