"""Acceptance tests for FEAT-025 decision record and outcome intent."""
import os
import uuid
os.environ["KAIZO_PERSISTENCE_MODE"]="postgres"
os.environ["DATABASE_URL"]="postgresql://postgres:postgres@localhost:5432/kaizo_test"
from fastapi.testclient import TestClient
import main, persistence
persistence.initialize()
client=TestClient(main.app)

def post(path,payload):
    r=client.post(path,json=payload)
    assert r.status_code in (200,201),(r.status_code,r.text)
    return r.json()

def build_reviewed_candidate():
    s=uuid.uuid4().hex[:8]
    a=post("/api/v1/athletes",{"display_name":f"FEAT025 Athlete {s}"})
    ass=post("/api/v1/assessments",{"athlete_id":a["athlete_id"],"template_id":"FEAT-025","measurements":{"score":5},"recorded_by":"coach-feat025"})
    p=post("/api/v1/problem-statements",{"athlete_id":a["athlete_id"],"assessment_id":ass["assessment_id"],"statement":"Decision record test","problem_type":"TECHNICAL","created_by":"coach-feat025"})
    e=post("/api/v1/evidence",{"evidence_id":f"FEAT025-EVID-{s}","subject_type":"problem","subject_id":p["problem_id"],"evidence_level":"E2","status":"VERIFIED","source_ref":"FEAT-025-TEST","claim":"Observed evidence","observed_value":{"score":5},"verified_by":"coach-feat025"})
    d=post(f"/api/v1/problem-statements/{p['problem_id']}/diagnosis",{"problem_id":p["problem_id"],"evidence_ids":[e["evidence_id"]],"diagnosis":"Test diagnosis","diagnosed_by":"coach-feat025"})
    c=post(f"/api/v1/diagnoses/{d['diagnosis_id']}/decision-candidates",{"diagnosis_id":d["diagnosis_id"],"requested_by":"coach-feat025"})["candidates"][0]
    post(f"/api/v1/decision-candidates/{c['candidate_id']}/coach-review",{"candidate_id":c["candidate_id"],"action":"CONFIRM","coach_id":"coach-feat025"})
    return c

def test_record_requires_coach_review():
    s=uuid.uuid4().hex[:8]
    a=post("/api/v1/athletes",{"display_name":f"FEAT025 NoReview {s}"})
    ass=post("/api/v1/assessments",{"athlete_id":a["athlete_id"],"template_id":"FEAT-025","measurements":{"score":3},"recorded_by":"coach-feat025"})
    p=post("/api/v1/problem-statements",{"athlete_id":a["athlete_id"],"assessment_id":ass["assessment_id"],"statement":"No review","problem_type":"TECHNICAL","created_by":"coach-feat025"})
    e=post("/api/v1/evidence",{"evidence_id":f"FEAT025-NR-{s}","subject_type":"problem","subject_id":p["problem_id"],"evidence_level":"E2","status":"VERIFIED","source_ref":"TEST","claim":"Evidence","observed_value":{"score":3},"verified_by":"coach-feat025"})
    d=post(f"/api/v1/problem-statements/{p['problem_id']}/diagnosis",{"problem_id":p["problem_id"],"evidence_ids":[e["evidence_id"]],"diagnosis":"Diagnosis","diagnosed_by":"coach-feat025"})
    c=post(f"/api/v1/diagnoses/{d['diagnosis_id']}/decision-candidates",{"diagnosis_id":d["diagnosis_id"],"requested_by":"coach-feat025"})["candidates"][0]
    r=client.post(f"/api/v1/decision-candidates/{c['candidate_id']}/decision-record",json={"candidate_id":c["candidate_id"],"coach_id":"coach-feat025","outcome_intent":"Improve the diagnosed technical outcome."})
    assert r.status_code==409

def test_record_and_readback():
    c=build_reviewed_candidate()
    r=post(f"/api/v1/decision-candidates/{c['candidate_id']}/decision-record",{"candidate_id":c["candidate_id"],"coach_id":"coach-feat025","decision_summary":"Apply the confirmed candidate.","outcome_intent":"Improve execution quality while validating the response."})
    assert r["status"]=="RECORDED"
    assert r["coach_action"]=="CONFIRM"
    assert r["outcome_intent"]
    assert r["coach_final_authority"] is True
    assert r["execution_authorized"] is False
    read=client.get(f"/api/v1/decision-candidates/{c['candidate_id']}/decision-record")
    assert read.status_code==200
    body=read.json()
    assert any(x["decision_id"]==r["decision_id"] for x in body["records"])
    assert body["execution_authorized"] is False

if __name__=="__main__":
    test_record_requires_coach_review()
    test_record_and_readback()
    print("FEAT-025 acceptance tests passed")
