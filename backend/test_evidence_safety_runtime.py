import os
os.environ["KAIZO_PERSISTENCE_MODE"]="memory"
from fastapi.testclient import TestClient
from main import app
client=TestClient(app)

def test_057_060_cycle():
    r=client.post("/api/v1/evidence-safety/feat-057/evidence-quality",json={"subject_id":"A1","evidence_level":"E3","quality_status":"VERIFIED","evidence_refs":["EV-1"],"assessed_by":"coach","coach_final_authority":True})
    assert r.status_code==201 and r.json()["execution_authorized"] is False
    r=client.post("/api/v1/evidence-safety/feat-058/provenance",json={"subject_id":"A1","provenance_refs":["SRC-1"],"disclosed_by":"coach","coach_final_authority":True})
    assert r.status_code==201
    r=client.post("/api/v1/evidence-safety/feat-059/block",json={"action_id":"ACT-1","block_reason":"insufficient safety evidence","diagnostic":{"required":"retest"},"evidence_refs":["EV-1"],"blocked_by":"coach","coach_final_authority":True})
    assert r.status_code==201 and r.json()["status"]=="HOLD"
    r=client.post("/api/v1/evidence-safety/feat-060/escalate",json={"subject_id":"A1","escalation_reason":"coach review required","review_state":"UNDER_REVIEW","escalated_by":"coach","evidence_refs":["EV-1"],"coach_final_authority":True})
    assert r.status_code==201

def test_quality_gates():
    r=client.post("/api/v1/evidence-safety/feat-057/evidence-quality",json={"subject_id":"A1","evidence_level":"E9","quality_status":"X","evidence_refs":["EV"],"assessed_by":"coach"})
    assert r.status_code==400
    r=client.post("/api/v1/evidence-safety/feat-059/block",json={"action_id":"ACT","block_reason":"x","diagnostic":{"x":1},"blocked_by":"coach","coach_final_authority":False})
    assert r.status_code==409
