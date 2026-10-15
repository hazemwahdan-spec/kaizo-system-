import pytest
from fastapi import HTTPException

from backend import phase4_identity_boundary as boundary
from productization.identity import IdentityNotConfiguredError, Principal


def verified_principal(role="coach", tenant_id="academy-a"):
    return Principal(
        actor_id="auth0|verified-user",
        role=role,
        tenant_id=tenant_id,
        resource_owner_id=None,
        verified=True,
        source="oidc_jwt",
    )


def test_identity_gate_defaults_to_closed(monkeypatch):
    monkeypatch.delenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", raising=False)
    with pytest.raises(HTTPException) as exc:
        boundary.require_phase4_principal("Bearer ignored")
    assert exc.value.status_code == 503


def test_identity_gate_rejects_invalid_bearer(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")

    def reject(_authorization):
        raise IdentityNotConfiguredError("invalid token")

    monkeypatch.setattr(boundary, "resolve_bearer_principal", reject)
    with pytest.raises(HTTPException) as exc:
        boundary.require_phase4_principal("Bearer invalid")
    assert exc.value.status_code == 401
    assert exc.value.headers["WWW-Authenticate"] == "Bearer"


def test_identity_gate_accepts_only_verified_oidc_principal(monkeypatch):
    monkeypatch.setenv("KAIZO_PHASE4_IDENTITY_ENFORCEMENT", "oidc")
    monkeypatch.setattr(boundary, "resolve_bearer_principal", lambda _: verified_principal())
    result = boundary.require_phase4_principal("Bearer signed-token")
    assert result.verified is True
    assert result.source == "oidc_jwt"


def test_role_allowlist_denies_unapproved_role():
    with pytest.raises(HTTPException) as exc:
        boundary.require_role(verified_principal(role="athlete"), {"coach"})
    assert exc.value.status_code == 403


def test_tenant_scope_denies_cross_tenant_resource():
    with pytest.raises(HTTPException) as exc:
        boundary.require_tenant_scope(verified_principal(), "academy-b")
    assert exc.value.status_code == 403


def test_tenant_scope_allows_matching_resource():
    result = boundary.require_tenant_scope(verified_principal(), "academy-a")
    assert result.tenant_id == "academy-a"
