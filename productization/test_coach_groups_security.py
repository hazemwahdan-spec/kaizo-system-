"""Coach training-group API authorization and membership regression tests."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"));sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from main import app
from productization import coach_roster,coach_groups

def headers(actor="coach-A",tenant="TENANT-A",role="coach"):
    return {"X-KAIZO-Actor":actor,"X-KAIZO-Role":role,"X-KAIZO-Tenant":tenant}
def setup_function():
    coach_roster.reset_memory_state();coach_groups.reset_memory_state()
def test_groups_require_verified_coach(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development")
    c=TestClient(app)
    assert c.get("/api/v1/product/coach/groups").status_code==401
    assert c.get("/api/v1/product/coach/groups",headers=headers(role="athlete")).status_code==403
def test_create_list_assign_unassign_and_audit_scope(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app)
    athlete=c.post("/api/v1/product/coach/athletes",json={"display_name":"Owned"},headers=headers()).json()
    group=c.post("/api/v1/product/coach/groups",json={"name":"U15"},headers=headers())
    assert group.status_code==201
    gid=group.json()["group_id"]
    assert c.post(f"/api/v1/product/coach/groups/{gid}/athletes",json={"athlete_id":athlete["athlete_id"]},headers=headers()).status_code==200
    data=c.get("/api/v1/product/coach/groups",headers=headers()).json()
    assert data["total"]==1 and data["groups"][0]["athletes"][0]["athlete_id"]==athlete["athlete_id"]
    assert c.delete(f"/api/v1/product/coach/groups/{gid}/athletes/{athlete['athlete_id']}",headers=headers()).status_code==200
    assert c.get("/api/v1/product/coach/groups",headers=headers()).json()["groups"][0]["athletes"]==[]
    assert any(x["action"]=="COACH_TRAINING_GROUP_ATHLETE_ASSIGNED" for x in coach_groups._AUDIT)
def test_cross_coach_and_cross_tenant_group_or_athlete_denied(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app)
    a=c.post("/api/v1/product/coach/athletes",json={"display_name":"A"},headers=headers()).json()
    b=c.post("/api/v1/product/coach/athletes",json={"display_name":"B"},headers=headers(actor="coach-B")).json()
    g=c.post("/api/v1/product/coach/groups",json={"name":"Own"},headers=headers()).json()["group_id"]
    assert c.post(f"/api/v1/product/coach/groups/{g}/athletes",json={"athlete_id":b["athlete_id"]},headers=headers()).status_code==404
    assert c.post(f"/api/v1/product/coach/groups/{g}/athletes",json={"athlete_id":a["athlete_id"]},headers=headers(actor="coach-B")).status_code==404
    assert c.get("/api/v1/product/coach/groups",headers=headers(actor="coach-B",tenant="TENANT-B")).json()["total"]==0
def test_request_cannot_spoof_actor_or_tenant(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development");c=TestClient(app)
    athlete=c.post("/api/v1/product/coach/athletes",json={"display_name":"Owned"},headers=headers()).json()
    gid=c.post("/api/v1/product/coach/groups",json={"name":"Scoped","tenant_id":"TENANT-B","coach_actor_id":"coach-B"},headers=headers()).json()["group_id"]
    denied=c.post(f"/api/v1/product/coach/groups/{gid}/athletes",json={"athlete_id":athlete["athlete_id"],"tenant_id":"TENANT-B","coach_actor_id":"coach-B"},headers=headers(actor="coach-B",tenant="TENANT-B"))
    assert denied.status_code==404
