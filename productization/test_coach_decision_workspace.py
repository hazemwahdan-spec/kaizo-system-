"""FEAT-009 Coach decision workspace API authorization and fail-closed tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
import main
import persistence
from productization import coach_roster

def headers(actor="coach-A", tenant="TENANT-A", role="coach"):
    return {"X-KAIZO-Actor": actor, "X-KAIZO-Role": role, "X-KAIZO-Tenant": tenant}

def setup_function():
    coach_roster.reset_memory_state()
    main.ASSESSMENT_RECORDS.clear()
    main.EVIDENCE_RECORDS.clear()
    main._ASSESSMENT_EVIDENCE_ATTACHMENTS.clear()

def create_athlete(client, h=None):
    response = client.post("/api/v1/product/coach/athletes",
                           json={"display_name": "Decision workspace athlete"},
                           headers=h or headers())
    assert response.status_code == 201
    return response.json()["athlete_id"]

def test_owner_gets_explicit_insufficient_evidence_when_durable_store_is_unavailable(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: False)
    client = TestClient(main.app)
    athlete_id = create_athlete(client)
    before = (dict(main.ASSESSMENT_RECORDS), dict(main.EVIDENCE_RECORDS),
              dict(main._ASSESSMENT_EVIDENCE_ATTACHMENTS))
    response = client.get(
        f"/api/v1/product/coach/athletes/{athlete_id}/decision-workspace",
        headers=headers(),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE"
    assert body["available"] is False
    assert body["assessments"] == [] and body["decisions"] == []
    assert body["read_only"] is True
    assert body["coach_final_authority"] is True
    assert body["execution_authorized"] is False
    assert before == (dict(main.ASSESSMENT_RECORDS), dict(main.EVIDENCE_RECORDS),
                      dict(main._ASSESSMENT_EVIDENCE_ATTACHMENTS))

def test_anonymous_and_non_coach_workspace_reads_are_denied(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: False)
    client = TestClient(main.app)
    athlete_id = create_athlete(client)
    url = f"/api/v1/product/coach/athletes/{athlete_id}/decision-workspace"
    assert client.get(url).status_code == 401
    assert client.get(url, headers=headers(role="athlete")).status_code == 403

def test_foreign_coach_and_tenant_receive_scoped_404(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: False)
    client = TestClient(main.app)
    athlete_id = create_athlete(client)
    url = f"/api/v1/product/coach/athletes/{athlete_id}/decision-workspace"
    assert client.get(url, headers=headers(actor="coach-B")).status_code == 404
    assert client.get(url, headers=headers(tenant="TENANT-B")).status_code == 404

def test_unknown_athlete_is_not_resolved_from_global_assessment_registry(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE", "development")
    monkeypatch.setattr(persistence, "is_postgres_enabled", lambda: False)
    client = TestClient(main.app)
    main.ASSESSMENT_RECORDS["GLOBAL-ASSESSMENT"] = {
        "assessment_id": "GLOBAL-ASSESSMENT", "athlete_id": "NOT-OWNED"
    }
    response = client.get(
        "/api/v1/product/coach/athletes/NOT-OWNED/decision-workspace",
        headers=headers(),
    )
    assert response.status_code == 404
