import os
os.environ["KAIZO_PERSISTENCE_MODE"]="memory"
from fastapi.testclient import TestClient
from main import app
client=TestClient(app)

def test_052_055_full_cycle():
    r=client.post("/api/v1/audit-trace/feat-052/trace",json={"actor_id":"coach-1","action":"DECISION_REVIEW","occurred_at":"2026-10-06T05:00:00Z","evidence_refs":["E-052"],"coach_final_authority":True})
    assert r.status_code==201 and r.json()["execution_authorized"] is False
    r=client.post("/api/v1/audit-trace/feat-053/governance",json={"object_id":"DEC-1","object_type":"decision","governance_status":"REVIEW","owner":"coach-1","metadata":{"scope":"judo"},"coach_final_authority":True})
    assert r.status_code==201
    r=client.post("/api/v1/audit-trace/feat-054/review",json={"query":"DEC-1","reviewed_by":"coach-1","coach_final_authority":True})
    assert r.status_code==200 and r.json()["results"]
    r=client.post("/api/v1/audit-trace/feat-055/trace",json={"product_action":"REPORT_GENERATED","source_record_ids":["DEC-1","TRACE-1"],"trace_reason":"approved source lineage","traced_by":"coach-1","coach_final_authority":True})
    assert r.status_code==201 and r.json()["execution_authorized"] is False

def test_governance_and_quality_gates():
    r=client.post("/api/v1/audit-trace/feat-052/trace",json={"actor_id":"coach-1","action":"X","coach_final_authority":False})
    assert r.status_code==409
    r=client.post("/api/v1/audit-trace/feat-055/trace",json={"product_action":"X","source_record_ids":[],"trace_reason":"r","traced_by":"coach-1","coach_final_authority":True})
    assert r.status_code==400
