import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"backend"));sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
import main
from main import app
from productization import coach_priority_queue


def h(actor="coach-A",tenant="TENANT-A",role="coach"):
    return {"X-KAIZO-Actor":actor,"X-KAIZO-Role":role,"X-KAIZO-Tenant":tenant}


def test_priority_queue_requires_verified_coach_and_is_read_only(monkeypatch):
    monkeypatch.setenv("KAIZO_IDENTITY_MODE","development")
    monkeypatch.setattr(coach_priority_queue,"get_coach_priority_queue",lambda **kw:{
        "available":False,"status":"INSUFFICIENT_EVIDENCE","items":[],
        "coach_final_authority":True,"execution_authorized":False})
    client=TestClient(app)
    assert client.get("/api/v1/product/coach/priority-queue").status_code==401
    assert client.get("/api/v1/product/coach/priority-queue",headers=h(role="athlete")).status_code==403
    before=dict(main.DECISION_RECORDS)
    response=client.get("/api/v1/product/coach/priority-queue",headers=h())
    assert response.status_code==200
    assert response.json()["status"]=="INSUFFICIENT_EVIDENCE"
    assert response.json()["execution_authorized"] is False
    assert dict(main.DECISION_RECORDS)==before
