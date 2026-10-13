"""Fail-closed tests for parent access to athlete progress."""
from fastapi import HTTPException
import pytest

from productization import product_api
from productization.product_surface import ProductSurface
from productization.runtime_adapter import RuntimeContext


def _request_parent_progress():
    return product_api.parent_progress(
        athlete_id="athlete-7",
        resource_tenant_id="academy-1",
        actor_id="header-parent-is-not-authoritative",
        role="parent",
        tenant_id="academy-1",
        owner=None,
        authorization="Bearer signed-token",
    )


def _install_verified_principal(monkeypatch, calls):
    def fake_ctx(actor_id, role, tenant_id, owner, authorization=None):
        calls["identity"] = {
            "actor_id": actor_id,
            "authorization": authorization,
        }
        return RuntimeContext(
            actor_id="oidc-parent-3",
            role="parent",
            tenant_id="academy-1",
            resource_owner_id=None,
        )

    monkeypatch.setattr(product_api, "ctx", fake_ctx)
    monkeypatch.setattr(product_api, "get_surface", lambda: ProductSurface(runtime=None))


def test_parent_progress_requires_verified_relationship_and_exact_scope_consent(monkeypatch):
    calls = {}
    _install_verified_principal(monkeypatch, calls)

    def verified_relationship(**kwargs):
        calls["relationship"] = kwargs
        return True

    def active_consent(**kwargs):
        calls["consent"] = kwargs
        return True

    monkeypatch.setattr(product_api, "has_verified_guardian_relationship", verified_relationship)
    monkeypatch.setattr(product_api, "has_active_child_consent", active_consent)

    result = _request_parent_progress()

    assert result["athlete_id"] == "athlete-7"
    assert result["approved_only"] is True
    assert calls["identity"]["authorization"] == "Bearer signed-token"
    assert calls["relationship"] == {
        "child_id": "athlete-7",
        "guardian_actor_id": "oidc-parent-3",
        "academy_id": "academy-1",
    }
    assert calls["consent"] == {
        "child_id": "athlete-7",
        "guardian_actor_id": "oidc-parent-3",
        "academy_id": "academy-1",
        "resource": "athlete_progress",
        "action": "read",
    }


def test_parent_progress_denies_missing_or_revoked_relationship(monkeypatch):
    calls = {}
    _install_verified_principal(monkeypatch, calls)
    monkeypatch.setattr(product_api, "has_verified_guardian_relationship", lambda **kwargs: False)
    monkeypatch.setattr(
        product_api,
        "has_active_child_consent",
        lambda **kwargs: pytest.fail("consent must not be evaluated without a verified relationship"),
    )

    with pytest.raises(HTTPException) as exc:
        _request_parent_progress()

    assert exc.value.status_code == 403
    assert "verified guardian relationship" in exc.value.detail


def test_parent_progress_denies_missing_revoked_or_expired_consent(monkeypatch):
    calls = {}
    _install_verified_principal(monkeypatch, calls)
    monkeypatch.setattr(product_api, "has_verified_guardian_relationship", lambda **kwargs: True)
    monkeypatch.setattr(product_api, "has_active_child_consent", lambda **kwargs: False)

    with pytest.raises(HTTPException) as exc:
        _request_parent_progress()

    assert exc.value.status_code == 403
    assert "active guardian consent" in exc.value.detail


def test_parent_progress_fails_closed_when_authoritative_store_is_unavailable(monkeypatch):
    calls = {}
    _install_verified_principal(monkeypatch, calls)

    def unavailable(**kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(product_api, "has_verified_guardian_relationship", unavailable)
    monkeypatch.setattr(product_api, "has_active_child_consent", lambda **kwargs: True)

    with pytest.raises(HTTPException) as exc:
        _request_parent_progress()

    assert exc.value.status_code == 503
    assert "store is unavailable" in exc.value.detail


def test_parent_progress_rejects_cross_tenant_before_guardian_lookup(monkeypatch):
    calls = {}

    def wrong_tenant(*args, **kwargs):
        return RuntimeContext(
            actor_id="oidc-parent-3",
            role="parent",
            tenant_id="another-academy",
            resource_owner_id=None,
        )

    monkeypatch.setattr(product_api, "ctx", wrong_tenant)
    monkeypatch.setattr(
        product_api,
        "has_verified_guardian_relationship",
        lambda **kwargs: pytest.fail("cross-tenant requests must be denied before relationship lookup"),
    )

    with pytest.raises(HTTPException) as exc:
        _request_parent_progress()

    assert exc.value.status_code == 403
    assert "cross-tenant" in exc.value.detail
