import os
os.environ["KAIZO_PERSISTENCE_MODE"]="memory"
from fastapi.testclient import TestClient
from main import app
client=TestClient(app)

def prov(k="K-1"):
    return client.post("/api/v1/knowledge-runtime/feat-047/provenance",json={"knowledge_id":k,"source_type":"IJF","source_ref":"REF-047","provenance_note":"verified technical source","evidence_refs":["E-047"],"changed_by":"coach-1","coach_final_authority":True})

def test_047_050_real_knowledge_cycle():
    r=prov(); assert r.status_code==201
    assert r.json()["record"]["lifecycle_status"]=="DRAFT"
    r=client.post("/api/v1/knowledge-runtime/feat-048/lifecycle",json={"knowledge_id":"K-1","lifecycle_status":"APPROVED","changed_by":"coach-1","coach_final_authority":True}); assert r.status_code==200
    r=client.post("/api/v1/knowledge-runtime/feat-049/retrieve",json={"workflow_context":"decision diagnosis","query":"K-1","requested_by":"coach-1","coach_final_authority":True})
    assert r.status_code==200 and len(r.json()["results"])==1
    r=client.post("/api/v1/knowledge-runtime/feat-050/link",json={"knowledge_id":"K-1","unit_id":"UNIT-1","link_type":"SUPPORTS","evidence_refs":["E-050"],"linked_by":"coach-1","coach_final_authority":True})
    assert r.status_code==201 and r.json()["link"]["execution_authorized"] is False

def test_governance_and_quality_gates():
    assert prov("K-2").status_code==201
    r=client.post("/api/v1/knowledge-runtime/feat-048/lifecycle",json={"knowledge_id":"K-2","lifecycle_status":"APPROVED","changed_by":"coach-1","coach_final_authority":False}); assert r.status_code==409
    r=client.post("/api/v1/knowledge-runtime/feat-050/link",json={"knowledge_id":"K-2","unit_id":"UNIT-2","link_type":"SUPPORTS","evidence_refs":["E"],"linked_by":"coach-1","coach_final_authority":True}); assert r.status_code==409
    r=prov("K-3"); assert r.status_code==201
    r=client.post("/api/v1/knowledge-runtime/feat-047/provenance",json={"knowledge_id":"K-4","source_type":"IJF","source_ref":"REF","provenance_note":"x","changed_by":"coach-1","coach_final_authority":True}); assert r.status_code==400
