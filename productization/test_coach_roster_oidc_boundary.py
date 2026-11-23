"""Memory-only Coach scope tests and fail-closed OIDC permission tests.

Successful memory-adapter requests use explicitly unverified test principals.
Verified Coach API requests require PostgreSQL and are exercised separately by
the disposable-PostgreSQL route integration test. JWT signature/issuer/audience
verification is covered by productization.identity tests.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from main import app
from productization import coach_roster, product_api
from productization.identity import IdentityNotConfiguredError, Principal


def client():
    return TestClient(app)


def verified(actor="auth0|coach-A", tenant="TENANT-A", role="coach", permissions=("product",)):
    return Principal(
        actor_id=actor,
        role=role,
        tenant_id=tenant,
        resource_owner_id=None,
        verified=True,
        source="oidc_jwt",
        permissions=frozenset(permissions),
    )

def _test_principal(actor="auth0|coach-A", tenant="TENANT-A", role="coach"):
    return Principal(
        actor_id=actor,
        role=role,
        tenant_id=tenant,
        resource_owner_id=None,
        verified=False,
        source="development_headers",
    )


@pytest.fixture(autouse=True)
def isolated_identity_and_roster(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_PERSISTENCE_MODE", "memory")
    coach_roster.reset_memory_state()


def test_stubbed_principal_ignores_spoofed_identity_headers(monkeypatch):
    monkeypatch.setattr(
        product_api,
        "resolve_bearer_principal",
        lambda authorization: _test_principal(),
    )
    response = client().post(
        "/api/v1/product/coach/athletes",
        headers={
            "Authorization": "Bearer signed-token",
            "X-KAIZO-Actor": "attacker",
            "X-KAIZO-Role": "athlete",
            "X-KAIZO-Tenant": "TENANT-ATTACKER",
        },
        json={"display_name": "OIDC-owned athlete"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False

    listing = client().get(
        "/api/v1/product/coach/athletes",
        headers={"Authorization": "Bearer signed-token"},
    )
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["athletes"][0]["display_name"] == "OIDC-owned athlete"


def test_stubbed_principal_cannot_read_another_coach_or_tenant(monkeypatch):
    principals = {
        "Bearer coach-A": _test_principal("auth0|coach-A", "TENANT-A"),
        "Bearer coach-B": _test_principal("auth0|coach-B", "TENANT-A"),
        "Bearer coach-C": _test_principal("auth0|coach-C", "TENANT-B"),
    }
    monkeypatch.setattr(
        product_api,
        "resolve_bearer_principal",
        lambda authorization: principals[authorization],
    )
    created = client().post(
        "/api/v1/product/coach/athletes",
        headers={"Authorization": "Bearer coach-A"},
        json={"display_name": "Private to Coach A"},
    )
    assert created.status_code == 201
    athlete_id = created.json()["athlete_id"]

    for token in ("Bearer coach-B", "Bearer coach-C"):
        response = client().get(
            f"/api/v1/product/coach/athletes/{athlete_id}",
            headers={"Authorization": token},
        )
        assert response.status_code == 404
        listing = client().get(
            "/api/v1/product/coach/athletes",
            headers={"Authorization": token},
        )
        assert listing.status_code == 200
        assert listing.json()["total"] == 0


def test_oidc_non_coach_principal_is_denied(monkeypatch):
    monkeypatch.setattr(
        product_api,
        "resolve_bearer_principal",
        lambda authorization: verified(role="athlete"),
    )
    response = client().get(
        "/api/v1/product/coach/athletes",
        headers={"Authorization": "Bearer athlete-token"},
    )
    assert response.status_code == 403


def test_oidc_missing_or_invalid_bearer_fails_closed(monkeypatch):
    def reject(_authorization):
        raise IdentityNotConfiguredError("OIDC token verification failed")

    monkeypatch.setattr(product_api, "resolve_bearer_principal", reject)
    response = client().get(
        "/api/v1/product/coach/athletes",
        headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401

def test_stubbed_coach_principal_uses_server_scope_without_client_identity_headers(monkeypatch):
    monkeypatch.setattr(
        product_api,
        "resolve_bearer_principal",
        lambda authorization: _test_principal(),
    )
    response = client().get(
        "/api/v1/product/coach/athletes",
        headers={"Authorization": "Bearer verified-coach-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 0
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False
    
def test_navigation_uses_stubbed_bearer_principal_without_client_identity_headers(monkeypatch):
    def resolve(actor_id, role, tenant_id, owner, authorization=None):
        assert actor_id == ""
        assert role == ""
        assert tenant_id == ""
        assert authorization == "Bearer verified-coach-token"
        return _test_principal()

    monkeypatch.setattr(product_api, "resolve_principal", resolve)
    response = client().get(
        "/api/v1/product/navigation",
        headers={"Authorization": "Bearer verified-coach-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "coach"
    assert body["execution_authorized"] is False
    assert body["coach_final_authority"] is True


def test_oidc_product_permission_is_required_for_coach_routes_and_navigation(monkeypatch):
    monkeypatch.setattr(
        product_api,
        "resolve_bearer_principal",
        lambda authorization: verified(permissions=()),
    )
    monkeypatch.setattr(
        product_api,
        "resolve_principal",
        lambda *args, **kwargs: verified(permissions=()),
    )
    headers = {"Authorization": "Bearer verified-without-product"}
    c = client()
    coach_roster_response = c.get("/api/v1/product/coach/athletes", headers=headers)
    navigation_response = c.get("/api/v1/product/navigation", headers=headers)
    assert coach_roster_response.status_code == 403
    assert coach_roster_response.json()["detail"] == "Product API permission required"
    assert navigation_response.status_code == 403
    assert navigation_response.json()["detail"] == "Product API permission required"
