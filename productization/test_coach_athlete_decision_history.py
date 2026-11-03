"""FEAT-005 Coach-scoped read-only athlete decision-cycle history tests."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"));sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
import main, training_workflow
from main import app
from productization import coach_roster

def headers(actor="coach-A",tenant="TENANT-A",role="coach"):
    return {"X-KAIZO-Actor":actor,"X-KAIZO-Role":role,"X-KAIZO-Tenant":tenant}

def setup_function():
    coach_roster.reset_memory_state()
    main.DECISION_RECORDS.clear()
    training_workflow._MEMORY.clear()

def create(c,h=None):
    r=c.post("/api/v1/product/coach/athletes",json={"display_name":"Decision history athlete"},headers=h or headers())
    assert r.status_code==201
    return r.json()["athlete_id"]

def seed_existing_cycle(athlete_id):
    decision_id="DECISION-EXISTING-001"
    main.DECISION_RECORDS[decision_id]={"decision_id":decision_id,"candidate_id":"CAND-1",
        "diagnosis_id":"DIAG-1","problem_id":"PROB-1","athlete_id":athlete_id,
        "assessment_id":"ASSESS-1","candidate_type":"TECHNICAL_ADAPTATION",
        "coach_action":"CONFIRM","coach_id":"coach-A","decision_summary":"Grip-entry timing",
        "outcome_intent":"Improve independent entry timing","status":"RECORDED",
        "recorded_at":"2026-10-20T10:00:00"}
    training_workflow._MEMORY["WF-1"]={"record_id":"WF-1","feature_id":"FEAT-033",
        "athlete_id":athlete_id,"decision_id":decision_id,"session_id":"SESSION-1",
        "payload":{"drill_id":"DRILL-1"},"created_by":"coach-A","created_at":"2026-10-21T10:00:00"}

def test_owner_reads_only_existing_decision_and_training_records(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app);aid=create(c)
    seed_existing_cycle(aid)
    result=c.get(f"/api/v1/product/coach/athletes/{aid}/decision-cycles",headers=headers())
    assert result.status_code==200
    body=result.json();assert body["total"]==1 and body["historical_backfill_performed"] is False
    cycle=body["cycles"][0]
    assert cycle["decision_id"]=="DECISION-EXISTING-001"
    assert cycle["training_records"][0]["feature_id"]=="FEAT-033"
    assert cycle["training_records"][0]["record_id"]=="WF-1"
    assert body["execution_authorized"] is False and body["coach_final_authority"] is True

def test_anonymous_and_non_coach_are_denied(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app)
    assert c.get("/api/v1/product/coach/athletes/a/decision-cycles").status_code==401
    assert c.get("/api/v1/product/coach/athletes/a/decision-cycles",headers=headers(role="athlete")).status_code==403

def test_foreign_coach_and_tenant_receive_scoped_404(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app);aid=create(c)
    seed_existing_cycle(aid)
    assert c.get(f"/api/v1/product/coach/athletes/{aid}/decision-cycles",headers=headers(actor="coach-B")).status_code==404
    assert c.get(f"/api/v1/product/coach/athletes/{aid}/decision-cycles",headers=headers(tenant="TENANT-B")).status_code==404

def test_history_is_read_only_and_does_not_create_or_backfill_cycles(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app);aid=create(c)
    before_decisions=dict(main.DECISION_RECORDS);before_workflow=dict(training_workflow._MEMORY)
    result=c.get(f"/api/v1/product/coach/athletes/{aid}/decision-cycles",headers=headers())
    assert result.status_code==200 and result.json()["cycles"]==[]
    assert main.DECISION_RECORDS==before_decisions
    assert training_workflow._MEMORY==before_workflow
    assert result.json()["historical_backfill_performed"] is False
