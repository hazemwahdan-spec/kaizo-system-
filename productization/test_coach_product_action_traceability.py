"""FEAT-055 unit and API security tests."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import main
import persistence
from productization import coach_action_history, coach_roster, coach_product_action_traceability

client = TestClient(main.app)


def headers(actor="coach-A", tenant="TENANT-A", role="coach"):
    return {"X-KAIZO-Actor": actor, "X-KAIZO-Role": role, "X-KAIZO-Tenant": tenant}


def setup_function():
    coach_roster.reset_memory_state()


def owned_athlete():
    return coach_roster.create_owned_athlete(
        tenant_id="TENANT-A", coach_actor_id="coach-A", display_name="Trace athlete"
    )


def test_trace_rejects_source_record_not_in_owned_coach_history(monkeypatch):
    athlete = owned_athlete()
    monkeypatch.setattr(coach_roster, "get_owned_athlete", lambda **kwargs: athlete)
    monkeypatch.setattr(coach_action_history, "get_coach_action_history", lambda **kwargs: {
        "available": True, "items": [{"source_record_id": "owned-1"}]
    })
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: True)
    monkeypatch.setattr(coach_product_action_traceability, "_ensure_schema", lambda: None)
    class Cursor:
        def execute(self, *args): pass
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
        def commit(self): pass
    monkeypatch.setattr(persistence, "connection", lambda: Connection())
    import pytest
    with pytest.raises(ValueError, match="Every source_record_id"):
        coach_product_action_traceability.create_coach_product_action_trace(
            tenant_id="TENANT-A", coach_actor_id="coach-A",
            athlete_id=athlete["athlete_id"], product_action="REPORT_CREATED",
            source_record_ids=["foreign-record"], trace_reason="test"
        )


def test_trace_refuses_memory_only_storage_without_claiming_creation(monkeypatch):
    athlete = owned_athlete()
    monkeypatch.setattr(coach_roster, "get_owned_athlete", lambda **kwargs: athlete)
    monkeypatch.setattr(coach_action_history, "get_coach_action_history", lambda **kwargs: {
        "available": True, "items": [{"source_record_id": "owned-1"}]
    })
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: False)
    result = coach_product_action_traceability.create_coach_product_action_trace(
        tenant_id="TENANT-A", coach_actor_id="coach-A",
        athlete_id=athlete["athlete_id"], product_action="REPORT_CREATED",
        source_record_ids=["owned-1"], trace_reason="verified source"
    )
    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["created"] is False


def test_trace_api_rejects_anonymous_noncoach_and_foreign_coach(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    athlete = owned_athlete()
    url = f"/api/v1/product/coach/athletes/{athlete['athlete_id']}/product-action-traces"
    payload = {"product_action": "REPORT_CREATED",
               "source_record_ids": ["owned-1"], "trace_reason": "test"}
    assert client.post(url, json=payload).status_code == 401
    assert client.post(url, json=payload, headers=headers(role="athlete")).status_code == 403
    assert client.post(url, json=payload, headers=headers(actor="coach-B")).status_code == 404
    assert client.get(url, headers=headers(actor="coach-B")).status_code == 404


def test_trace_api_rejects_empty_source_ids(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    athlete = owned_athlete()
    response = client.post(
        f"/api/v1/product/coach/athletes/{athlete['athlete_id']}/product-action-traces",
        json={"product_action": "REPORT_CREATED", "source_record_ids": [],
              "trace_reason": "test"}, headers=headers()
    )
    assert response.status_code == 422


def test_trace_api_does_not_trust_caller_supplied_traced_by(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    athlete = owned_athlete()
    monkeypatch.setattr(coach_action_history, "get_coach_action_history", lambda **kwargs: {
        "available": False, "items": []
    })
    response = client.post(
        f"/api/v1/product/coach/athletes/{athlete['athlete_id']}/product-action-traces",
        json={"product_action": "REPORT_CREATED", "source_record_ids": ["forged"],
              "trace_reason": "test", "traced_by": "attacker"}, headers=headers()
    )
    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "INSUFFICIENT_EVIDENCE"
