"""Retired unscoped athlete creation must never write data or audit attribution."""
from fastapi.testclient import TestClient

import main
from productization.identity import Principal


client = TestClient(main.app)


def _principal():
    return Principal(
        actor_id="auth0|academy-a-service",
        role="academy",
        tenant_id="academy-a",
        resource_owner_id=None,
        verified=True,
        source="oidc_jwt",
    )


def _assert_retired_without_writes(monkeypatch, authorization):
    monkeypatch.setattr(main, "resolve_bearer_principal", lambda _: _principal())
    monkeypatch.setattr(main.persistence, "is_postgres_enabled", lambda: True)
    upserts = []
    tenant_audits = []
    unscoped_audits = []
    monkeypatch.setattr(main.persistence, "upsert_athlete", lambda record: upserts.append(record))
    monkeypatch.setattr(main.persistence, "append_tenant_audit", lambda **kwargs: tenant_audits.append(kwargs))
    monkeypatch.setattr(main.persistence, "append_audit", lambda **kwargs: unscoped_audits.append(kwargs))

    response = client.post(
        "/api/v1/athletes",
        headers={"Authorization": authorization},
        json={"display_name": "Test Athlete", "metadata": {"tenant_id": "academy-b"}},
    )

    assert response.status_code == 410
    assert upserts == []
    assert tenant_audits == []
    assert unscoped_audits == []


def test_verified_academy_cannot_use_retired_unscoped_athlete_write(monkeypatch):
    _assert_retired_without_writes(monkeypatch, "Bearer signed-academy-token")


def test_request_payload_cannot_reactivate_retired_route_or_select_audit_tenant(monkeypatch):
    _assert_retired_without_writes(monkeypatch, "Bearer signed-academy-token")


def test_invalid_bearer_cannot_use_retired_route_or_receive_audit_attribution(monkeypatch):
    from productization.identity import IdentityNotConfiguredError

    def reject(_authorization):
        raise IdentityNotConfiguredError("invalid token")

    monkeypatch.setattr(main, "resolve_bearer_principal", reject)
    monkeypatch.setattr(main.persistence, "is_postgres_enabled", lambda: True)
    upserts = []
    audits = []
    monkeypatch.setattr(main.persistence, "upsert_athlete", lambda record: upserts.append(record))
    monkeypatch.setattr(main.persistence, "append_audit", lambda **kwargs: audits.append(kwargs))

    response = client.post(
        "/api/v1/athletes",
        headers={"Authorization": "Bearer invalid"},
        json={"display_name": "Unscoped Test Athlete", "metadata": {}},
    )

    assert response.status_code == 410
    assert upserts == []
    assert audits == []
