"""Regression tests for tenant audit authentication and authorization."""
from fastapi import HTTPException
import pytest

import audit_authorization as auth
from productization.identity import IdentityNotConfiguredError, Principal


def test_missing_or_invalid_identity_is_401(monkeypatch):
    def reject(_authorization):
        raise IdentityNotConfiguredError("invalid")
    monkeypatch.setattr(auth, "resolve_bearer_principal", reject)
    with pytest.raises(HTTPException) as error:
        auth.require_tenant_audit_reader("Bearer bad")
    assert error.value.status_code == 401
    assert error.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("role", ["coach", "athlete", "parent", "publisher"])
def test_non_academy_role_is_forbidden(monkeypatch, role):
    monkeypatch.setattr(auth, "resolve_bearer_principal", lambda _: Principal(
        actor_id="actor", role=role, tenant_id="tenant-a",
        resource_owner_id=None, verified=True, source="oidc_jwt"))
    with pytest.raises(HTTPException) as error:
        auth.require_tenant_audit_reader("Bearer valid")
    assert error.value.status_code == 403


def test_unverified_identity_is_rejected(monkeypatch):
    monkeypatch.setattr(auth, "resolve_bearer_principal", lambda _: Principal(
        actor_id="actor", role="academy", tenant_id="tenant-a",
        resource_owner_id=None, verified=False, source="development_headers"))
    with pytest.raises(HTTPException) as error:
        auth.require_tenant_audit_reader("Bearer unverified")
    assert error.value.status_code == 401


def test_academy_principal_is_returned_with_claimed_tenant_only(monkeypatch):
    principal = Principal(actor_id="academy-1", role="academy", tenant_id="tenant-a",
                          resource_owner_id=None, verified=True, source="oidc_jwt")
    monkeypatch.setattr(auth, "resolve_bearer_principal", lambda _: principal)
    assert auth.require_tenant_audit_reader("Bearer valid") is principal
    assert principal.tenant_id == "tenant-a"
