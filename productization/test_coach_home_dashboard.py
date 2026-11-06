"""FEAT-006 Coach home dashboard: ownership, scope and truthful-data tests."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"));sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
import main
from main import app
from productization import coach_roster, coach_groups

def h(actor="coach-A",tenant="TENANT-A",role="coach"):
    return {"X-KAIZO-Actor":actor,"X-KAIZO-Role":role,"X-KAIZO-Tenant":tenant}

def setup_function():
    coach_roster.reset_memory_state();coach_groups.reset_memory_state();main.DECISION_RECORDS.clear()

def add_athlete(c,name,headers):
    r=c.post("/api/v1/product/coach/athletes",json={"display_name":name},headers=headers)
    assert r.status_code==201
    return r.json()["athlete_id"]

def test_dashboard_summarizes_only_verified_coach_owned_records(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app)
    a1=add_athlete(c,"A active",h());a2=add_athlete(c,"B active",h())
    foreign=add_athlete(c,"Foreign coach",h(actor="coach-B"))
    other=add_athlete(c,"Other tenant",h(actor="coach-C",tenant="TENANT-B"))
    c.patch(f"/api/v1/product/coach/athletes/{a2}/status",json={"status":"SUSPENDED","reason":"Dashboard test"},headers=h())
    group=c.post("/api/v1/product/coach/groups",json={"name":"U15"},headers=h()).json()
    assert c.post(f"/api/v1/product/coach/groups/{group['group_id']}/athletes",json={"athlete_id":a1},headers=h()).status_code==200
    main.DECISION_RECORDS["D-A"]={"decision_id":"D-A","athlete_id":a1,"decision_summary":"Entry timing","status":"RECORDED","recorded_at":"2026-11-01T10:00:00","coach_action":"CONFIRM"}
    main.DECISION_RECORDS["D-FOREIGN"]={"decision_id":"D-FOREIGN","athlete_id":foreign,"decision_summary":"Foreign","status":"RECORDED","recorded_at":"2026-11-02T10:00:00"}
    main.DECISION_RECORDS["D-OTHER"]={"decision_id":"D-OTHER","athlete_id":other,"decision_summary":"Other tenant","status":"RECORDED","recorded_at":"2026-11-03T10:00:00"}
    r=c.get("/api/v1/product/coach/dashboard",headers=h())
    assert r.status_code==200;d=r.json()
    assert d["athlete_total"]==2
    assert d["athlete_status_counts"]["ACTIVE"]==1 and d["athlete_status_counts"]["SUSPENDED"]==1
    assert d["training_group_total"]==1 and d["group_membership_total"]==1
    assert d["decision_cycle_total"]==1 and d["recent_decisions"][0]["decision_id"]=="D-A"
    assert d["priority_queue"]=={"available":False,"feature":"FEAT-007"}
    assert d["coach_final_authority"] is True and d["execution_authorized"] is False

def test_dashboard_requires_verified_coach_and_rejects_other_roles(monkeypatch):
    monkeypatch.delenv("KAIZO_IDENTITY_MODE",raising=False);c=TestClient(app)
    assert c.get("/api/v1/product/coach/dashboard").status_code==401
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development")
    assert c.get("/api/v1/product/coach/dashboard",headers=h(role="athlete")).status_code==403

def test_dashboard_is_read_only(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app)
    aid=add_athlete(c,"Read only",h())
    before=(dict(main.DECISION_RECORDS),len(coach_roster._MEMORY_AUDIT),len(coach_groups._AUDIT))
    r=c.get("/api/v1/product/coach/dashboard",headers=h())
    after=(dict(main.DECISION_RECORDS),len(coach_roster._MEMORY_AUDIT),len(coach_groups._AUDIT))
    assert r.status_code==200 and before==after
    assert r.json()["athlete_total"]==1
