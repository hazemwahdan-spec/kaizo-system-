"""HTTP-level contract tests for Phase 4 identity primitives.

These tests exercise FastAPI dependency behavior in a focused harness. They do
not claim the dependency is wired to the production Core API routes.
"""
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from backend import phase4_identity_boundary as boundary
from productization.identity import IdentityNotConfiguredError, Principal


def principal(role="coach", tenant_id="academy-a"):
    return Principal(
        actor_id="oidc|test-subject",
        role=role,
        tenant_id=tenant_id,
        resource_owner_id=None,
        verified=True,
        source="oidc_jwt",
    )


app = FastAPI()


@app.get("/protected")
def protected(
    authorization: str | None = Header(default=None),
    current: Principal = Depends(boundary.require_phase4_principal),
):
    boundary.require_role(current, {"coach", "academy"})
    boundary.require_tenant_scope(current, "academy-a")
    return {"actor_id": current.actor_id, "tenant_id": current.tenant_id}


client = TestClient(app)


def test_http_gate_is_closed_when_not_configured(monkeypatch):
    monkeypatch.delenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", raising=False)
    response = client.get("/protected", headers={"Authorization": "Bearer token"})
    assert response.status_code == 503


def test_http_invalid_bearer_is_rejected_without_handler_execution(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")

    def reject(_authorization):
        raise IdentityNotConfiguredError("invalid token")

    monkeypatch.setattr(boundary, "resolve_bearer_principal", reject)
    response = client.get("/protected", headers={"Authorization": "Bearer invalid"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_http_verified_principal_is_accepted_for_matching_scope(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal())
    response = client.get("/protected", headers={"Authorization": "Bearer signed"})
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "academy-a"


def test_http_disallowed_role_is_denied(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal(role="athlete"))

    @app.get("/role-denied")
    def role_denied(current: Principal = Depends(boundary.require_phase4_principal)):
        boundary.require_role(current, {"coach"})
        return {"allowed": True}

    response = client.get("/role-denied", headers={"Authorization": "Bearer signed"})
    assert response.status_code == 403


def test_http_cross_tenant_scope_is_denied(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: principal(tenant_id="academy-b"))

    response = client.get("/protected", headers={"Authorization": "Bearer signed"})
    assert response.status_code == 403
