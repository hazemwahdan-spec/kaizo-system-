"""FEAT-054 Coach audit-review endpoint security and behavior tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import main
from productization import coach_action_history, coach_roster


def headers(actor="coach-A", tenant="TENANT-A", role="coach"):
    return {"X-KAIZO-Actor": actor, "X-KAIZO-Role": role, "X-KAIZO-Tenant": tenant}


def setup_function():
    coach_roster.reset_memory_state()


def create_athlete(client):
    response = client.post("/api/v1/product/coach/athletes",
                           json={"display_name": "Audit review athlete"},
                           headers=headers())
    assert response.status_code == 201
    return response.json()["athlete_id"]


def test_review_filters_only_the_owned_history_and_attributes_verified_coach(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    client = TestClient(main.app)
    athlete_id = create_athlete(client)
    monkeypatch.setattr(coach_action_history, "get_coach_action_history", lambda **kwargs: {
        "available": True,
        "items": [
            {"source": "TENANT_SCOPED_AUDIT", "source_record_id": "1",
             "actor_id": "coach-A", "action": "COACH_DECISION_RECORDED",
             "reason": "Reviewed Seoi-nage entry", "actor_attribution_verified": True},
            {"source": "TENANT_SCOPED_AUDIT", "source_record_id": "2",
             "actor_id": "coach-A", "action": "COACH_ATHLETE_STATUS_CHANGED",
             "reason": "Status updated", "actor_attribution_verified": True},
        ],
    })
    response = client.get(
        f"/api/v1/product/coach/athletes/{athlete_id}/audit-review",
        params={"query": "seoi"},
        headers=headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["feature_id"] == "FEAT-054"
    assert body["status"] == "MATCHES_FOUND"
    assert body["result_count"] == 1
    assert body["results"][0]["source_record_id"] == "1"
    assert body["reviewed_by"] == "coach-A"
    assert body["reviewed_by_verified"] is True
    assert body["read_only"] is True
    assert body["execution_authorized"] is False


def test_review_rejects_anonymous_noncoach_and_foreign_athlete(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    client = TestClient(main.app)
    athlete_id = create_athlete(client)
    url = f"/api/v1/product/coach/athletes/{athlete_id}/audit-review"
    assert client.get(url, params={"query": "x"}).status_code == 401
    assert client.get(url, params={"query": "x"}, headers=headers(role="athlete")).status_code == 403
    assert client.get(url, params={"query": "x"}, headers=headers(actor="coach-B")).status_code == 404


def test_review_returns_insufficient_evidence_without_durable_history(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    client = TestClient(main.app)
    athlete_id = create_athlete(client)
    monkeypatch.setattr(coach_action_history, "get_coach_action_history", lambda **kwargs: {
        "available": False, "status": "INSUFFICIENT_EVIDENCE", "items": []
    })
    response = client.get(
        f"/api/v1/product/coach/athletes/{athlete_id}/audit-review",
        params={"query": "anything"}, headers=headers(),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "INSUFFICIENT_EVIDENCE"
    assert response.json()["results"] == []


def test_review_requires_nonempty_query(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    client = TestClient(main.app)
    athlete_id = create_athlete(client)
    response = client.get(
        f"/api/v1/product/coach/athletes/{athlete_id}/audit-review",
        params={"query": "   "}, headers=headers(),
    )
    assert response.status_code == 422




def test_review_excludes_records_without_verified_actor_attribution(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    client = TestClient(main.app)
    athlete_id = create_athlete(client)
    monkeypatch.setattr(coach_action_history, "get_coach_action_history", lambda **kwargs: {
        "available": True,
        "items": [
            {"source": "TENANT_SCOPED_AUDIT", "source_record_id": "verified",
             "action": "COACH_DECISION_RECORDED", "reason": "verified event",
             "actor_attribution_verified": True},
            {"source": "FEAT-044_DECISION_STATE_LINK", "source_record_id": "unverified",
             "action": "DECISION_STATE_LINK_RECORDED", "reason": "unverified link",
             "actor_attribution_verified": False},
        ],
    })
    response = client.get(
        f"/api/v1/product/coach/athletes/{athlete_id}/audit-review",
        params={"query": "recorded"}, headers=headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result_count"] == 1
    assert body["results"][0]["source_record_id"] == "verified"
