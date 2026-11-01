"""Verified request identity must be the source of tenant-scoped audit writes."""
from fastapi.testclient import TestClient

import main
from productization.identity import Principal


client = TestClient(main.app)


def test_verified_academy_identity_scopes_audit_write(monkeypatch):
    principal = Principal(
        actor_id="auth0|academy-a-service",
        role="academy",
        tenant_id="academy-a",
        resource_owner_id=None,
        verified=True,
        source="oidc_jwt",
    )
    monkeypatch.setattr(main, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(main.persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(main.persistence, "upsert_athlete", lambda _record: None)
    writes = []
    monkeypatch.setattr(
        main.persistence,
        "append_tenant_audit",
        lambda **kwargs: writes.append(kwargs),
    )

    response = client.post(
        "/api/v1/athletes",
        headers={"Authorization": "Bearer signed-academy-token"},
        json={"display_name": "Test Athlete", "metadata": {}},
    )

    assert response.status_code == 201
    assert len(writes) == 1
    assert writes[0]["tenant_id"] == "academy-a"
    assert writes[0]["who"] == "auth0|academy-a-service"
    assert writes[0]["action"] == "ATHLETE_CREATED"


def test_request_payload_cannot_select_audit_tenant(monkeypatch):
    principal = Principal(
        actor_id="auth0|academy-a-service",
        role="academy",
        tenant_id="academy-a",
        resource_owner_id=None,
        verified=True,
        source="oidc_jwt",
    )
    monkeypatch.setattr(main, "resolve_bearer_principal", lambda _: principal)
    monkeypatch.setattr(main.persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(main.persistence, "upsert_athlete", lambda _record: None)
    writes = []
    monkeypatch.setattr(
        main.persistence,
        "append_tenant_audit",
        lambda **kwargs: writes.append(kwargs),
    )

    response = client.post(
        "/api/v1/athletes",
        headers={"Authorization": "Bearer signed-academy-token"},
        json={
            "display_name": "Test Athlete",
            "metadata": {"tenant_id": "academy-b"},
        },
    )

    assert response.status_code == 201
    assert writes[0]["tenant_id"] == "academy-a"


def test_invalid_bearer_never_receives_tenant_attribution(monkeypatch):
    from productization.identity import IdentityNotConfiguredError

    def reject(_authorization):
        raise IdentityNotConfiguredError("invalid token")

    monkeypatch.setattr(main, "resolve_bearer_principal", reject)
    monkeypatch.setattr(main.persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(main.persistence, "upsert_athlete", lambda _record: None)
    unscoped_writes = []
    monkeypatch.setattr(
        main.persistence,
        "append_audit",
        lambda **kwargs: unscoped_writes.append(kwargs),
    )

    response = client.post(
        "/api/v1/athletes",
        headers={"Authorization": "Bearer invalid"},
        json={"display_name": "Unscoped Test Athlete", "metadata": {}},
    )

    assert response.status_code == 201
    assert len(unscoped_writes) == 1
    assert "tenant_id" not in unscoped_writes[0]
