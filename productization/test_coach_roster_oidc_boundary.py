"""OIDC route-boundary tests for the Coach-owned athlete roster.

The resolver is stubbed only at the verified-principal boundary. These tests
prove that the API uses claims returned by the verifier and ignores caller
identity headers; JWT signature/issuer/audience verification is covered by
productization.identity and the live Auth0 workflow.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

import pytest
from fastapi.testclient import TestClient

from main import app
from productization import coach_roster, product_api, identity
from productization.identity import IdentityNotConfiguredError, Principal


def client():
    return TestClient(app)


def verified(actor="auth0|coach-A", tenant="TENANT-A", role="coach"):
    return Principal(
        actor_id=actor,
        role=role,
        tenant_id=tenant,
        resource_owner_id=None,
        verified=True,
        source="oidc_jwt",
    )


@pytest.fixture(autouse=True)
def isolated_identity_and_roster(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "oidc")
    monkeypatch.setenv("KAIZO_PERSISTENCE_MODE", "memory")
    coach_roster.reset_memory_state()


def test_oidc_claims_override_spoofed_identity_headers(monkeypatch):
    monkeypatch.setattr(
        product_api,
        "resolve_bearer_principal",
        lambda authorization: verified(),
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


def test_oidc_principal_cannot_read_another_coach_or_tenant(monkeypatch):
    principals = {
        "Bearer coach-A": verified("auth0|coach-A", "TENANT-A"),
        "Bearer coach-B": verified("auth0|coach-B", "TENANT-A"),
        "Bearer coach-C": verified("auth0|coach-C", "TENANT-B"),
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

def test_oidc_navigation_uses_verified_claims_without_client_identity_headers(monkeypatch):
    monkeypatch.setattr(
        identity,
        "resolve_bearer_principal",
        lambda authorization: verified(),
    )
    response = client().get(
        "/api/v1/product/navigation",
        headers={"Authorization": "Bearer verified-coach-token"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "coach"
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False
