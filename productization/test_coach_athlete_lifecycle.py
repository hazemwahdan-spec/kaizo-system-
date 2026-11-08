"""FEAT-004 security and lifecycle tests for Coach-owned athletes."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"));sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from main import app
from productization import coach_roster

def headers(actor="coach-A",tenant="TENANT-A",role="coach"):
    return {"X-KAIZO-Actor":actor,"X-KAIZO-Role":role,"X-KAIZO-Tenant":tenant}
def setup_function():
    coach_roster.reset_memory_state()
def create(c,h=None,name="Lifecycle athlete"):
    r=c.post("/api/v1/product/coach/athletes",json={"display_name":name},headers=h or headers())
    assert r.status_code==201
    return r.json()["athlete_id"]

def test_status_change_requires_verified_coach(monkeypatch):
    monkeypatch.delenv("KAIZO_IDENTITY_MODE",raising=False);c=TestClient(app)
    assert c.patch("/api/v1/product/coach/athletes/x/status",json={"status":"INACTIVE","reason":"x"}).status_code==401
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development")
    assert c.patch("/api/v1/product/coach/athletes/x/status",json={"status":"INACTIVE","reason":"x"},headers=headers(role="athlete")).status_code==403

def test_valid_lifecycle_transitions_and_history(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app);aid=create(c)
    r=c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json={"status":"SUSPENDED","reason":"Temporary injury break"},headers=headers())
    assert r.status_code==200 and r.json()["status"]=="SUSPENDED" and r.json()["previous_status"]=="ACTIVE"
    r=c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json={"status":"ACTIVE","reason":"Cleared to resume"},headers=headers())
    assert r.status_code==200 and r.json()["status"]=="ACTIVE"
    detail=c.get(f"/api/v1/product/coach/athletes/{aid}",headers=headers()).json()
    assert detail["status"]=="ACTIVE"
    history=c.get(f"/api/v1/product/coach/athletes/{aid}/status-history",headers=headers()).json()
    assert history["total"]==2
    assert [x["new_status"] for x in history["history"]]==["SUSPENDED","ACTIVE"]
    assert history["history"][0]["reason"]=="Temporary injury break"

def test_invalid_transition_and_missing_reason_are_rejected(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app);aid=create(c)
    assert c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json={"status":"UNKNOWN","reason":"x"},headers=headers()).status_code==422
    assert c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json={"status":"INACTIVE","reason":" "},headers=headers()).status_code==422
    assert c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json={"status":"ARCHIVED","reason":"Closed"},headers=headers()).status_code==200
    assert c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json={"status":"ACTIVE","reason":"Reactivate"},headers=headers()).status_code==422

def test_foreign_coach_cannot_change_or_read_lifecycle(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app);aid=create(c)
    assert c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json={"status":"INACTIVE","reason":"x"},headers=headers(actor="coach-B")).status_code==404
    assert c.get(f"/api/v1/product/coach/athletes/{aid}/status-history",headers=headers(actor="coach-B")).status_code==404
    assert c.get(f"/api/v1/product/coach/athletes/{aid}",headers=headers()).json()["status"]=="ACTIVE"

def test_body_cannot_spoof_owner_or_tenant_and_noop_is_idempotent(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app);aid=create(c)
    payload={"status":"INACTIVE","reason":"Coach decision","tenant_id":"TENANT-B","coach_actor_id":"coach-B"}
    r=c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json=payload,headers=headers())
    assert r.status_code==200
    again=c.patch(f"/api/v1/product/coach/athletes/{aid}/status",json=payload,headers=headers())
    assert again.status_code==200 and again.json()["changed"] is False
    assert c.get(f"/api/v1/product/coach/athletes/{aid}/status-history",headers=headers()).json()["total"]==1
