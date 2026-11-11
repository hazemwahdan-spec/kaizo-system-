"""Security regression tests for the Coach-owned athlete roster."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app
from productization import coach_roster


def client():
    return TestClient(app)


def auth_headers(actor="coach-A", tenant="TENANT-A", role="coach"):
    return {"X-KAIZO-Actor": actor, "X-KAIZO-Role": role, "X-KAIZO-Tenant": tenant}


def setup_function():
    coach_roster.reset_memory_state()


def test_anonymous_roster_access_fails_closed(monkeypatch):
    monkeypatch.delenv("KAIZO_IDENTITY_MODE", raising=False)
    response = client().get("/api/v1/product/coach/athletes")
    assert response.status_code == 401


def test_non_coach_cannot_create_or_list_coach_roster(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    c = client()
    headers = auth_headers(role="athlete")
    assert c.get("/api/v1/product/coach/athletes", headers=headers).status_code == 403
    assert c.post("/api/v1/product/coach/athletes",
                  json={"display_name": "Not a coach"}, headers=headers).status_code == 403


def test_coach_sees_only_owned_athletes_in_same_tenant(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    c = client()
    a = c.post("/api/v1/product/coach/athletes",
               json={"display_name": "Owned by A"}, headers=auth_headers())
    b = c.post("/api/v1/product/coach/athletes",
               json={"display_name": "Owned by B"},
               headers=auth_headers(actor="coach-B"))
    other_tenant = c.post("/api/v1/product/coach/athletes",
                          json={"display_name": "Other tenant"},
                          headers=auth_headers(actor="coach-C", tenant="TENANT-B"))
    assert a.status_code == 201
    assert b.status_code == 201
    assert other_tenant.status_code == 201
    assert [x["display_name"] for x in c.get(
        "/api/v1/product/coach/athletes", headers=auth_headers()
    ).json()["athletes"]] == ["Owned by A"]
    athlete_id = b.json()["athlete_id"]
    assert c.get(f"/api/v1/product/coach/athletes/{athlete_id}",
                 headers=auth_headers()).status_code == 404


def test_legacy_unscoped_athlete_creation_is_retired_and_cannot_create_unowned_records(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    c = client()
    legacy = c.post("/api/v1/athletes", json={"display_name": "Legacy unassigned"})
    assert legacy.status_code == 410
    assert c.get("/api/v1/product/coach/athletes",
                 headers=auth_headers()).json()["total"] == 0


def test_each_coach_receives_only_their_server_created_athletes(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    c = client()
    a = c.post("/api/v1/product/coach/athletes",
               json={"display_name": "Coach A"}, headers=auth_headers())
    b = c.post("/api/v1/product/coach/athletes",
               json={"display_name": "Coach B"},
               headers=auth_headers(actor="coach-B"))
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["athlete_id"] != b.json()["athlete_id"]
    assert c.get(f"/api/v1/product/coach/athletes/{b.json()['athlete_id']}",
                 headers=auth_headers()).status_code == 404


def test_caller_cannot_override_verified_scope_with_body_or_query(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    c = client()
    created = c.post("/api/v1/product/coach/athletes",
                     json={"display_name": "Scoped", "tenant_id": "TENANT-B",
                           "coach_actor_id": "coach-B"},
                     headers=auth_headers())
    assert created.status_code == 201
    athlete_id = created.json()["athlete_id"]
    assert c.get(f"/api/v1/product/coach/athletes/{athlete_id}",
                 params={"tenant_id": "TENANT-B", "coach_actor_id": "coach-B"},
                 headers=auth_headers()).status_code == 200
    assert c.get(f"/api/v1/product/coach/athletes/{athlete_id}",
                 headers=auth_headers(actor="coach-B", tenant="TENANT-B")).status_code == 404
