import os
os.environ["KAIZO_PERSISTENCE_MODE"]="memory"

from fastapi.testclient import TestClient
from main import app
from feature_runtime import CONTRACTS

client=TestClient(app)

def test_all_missing_features_have_real_contracts():
    expected={f"FEAT-{i:03d}" for i in range(29,76)} - {"FEAT-041","FEAT-046","FEAT-051","FEAT-056"}
    assert set(CONTRACTS)==expected
    for fid, contract in CONTRACTS.items():
        assert contract["name"]
        assert contract["required"]

def test_feature_record_enforces_governance_and_required_fields():
    r=client.post("/api/v1/features/feat-034/drill-prescription",json={
        "subject_id":"athlete-1","actor_id":"coach-1","payload":{},
        "coach_final_authority":True,"execution_authorized":False})
    assert r.status_code==400
    assert "missing_fields" in r.json()["detail"]

    r=client.post("/api/v1/features/feat-034/drill-prescription",json={
        "subject_id":"athlete-1","actor_id":"coach-1",
        "payload":{"drill_id":"D1","session_id":"S1","dosage":"3x5","rationale":"technical quality"},
        "coach_final_authority":False,"execution_authorized":False})
    assert r.status_code==409

    r=client.post("/api/v1/features/feat-034/drill-prescription",json={
        "subject_id":"athlete-1","actor_id":"coach-1",
        "payload":{"drill_id":"D1","session_id":"S1","dosage":"3x5","rationale":"technical quality"},
        "coach_final_authority":True,"execution_authorized":False})
    assert r.status_code==201
    record=r.json()
    assert record["feature_id"]=="FEAT-034"
    assert record["coach_final_authority"] is True
    assert record["execution_authorized"] is False

def test_evidence_required_features_hold_without_evidence():
    r=client.post("/api/v1/features/feat-031/drill-library",json={
        "subject_id":"drill-1","actor_id":"coach-1",
        "payload":{
            "drill_id":"D1","name":"uchi-komi","judo_area":"Nage-waza",
            "technical_skill":"Seoi-nage entry","problem_target":"late entry",
            "decision_target":"entry timing","age_suitability":"U11+",
            "skill_level":"intermediate","execution_pattern":"controlled repetitions",
            "kpi":"entry quality","safety_constraints":"coach supervised"
        },
        "coach_final_authority":True,"execution_authorized":False})
    assert r.status_code==400
    assert "evidence_refs" in str(r.json()["detail"])

def test_feature_list_and_get():
    r=client.post("/api/v1/features/feat-061/academy-entity",json={
        "subject_id":"academy-1","actor_id":"admin-1",
        "payload":{"academy_id":"academy-1","name":"KAIZO Academy","status":"ACTIVE"},
        "coach_final_authority":True,"execution_authorized":False})
    assert r.status_code==201
    rid=r.json()["record_id"]
    g=client.get(f"/api/v1/features/feat-061/academy-entity/{rid}")
    assert g.status_code==200
    l=client.get("/api/v1/features/feat-061/academy-entity")
    assert l.status_code==200
    assert any(x["record_id"]==rid for x in l.json()["records"])


def test_canonical_domain_validation_is_enforced():
    r=client.post("/api/v1/features/feat-029/progression-regression-rules",json={
        "subject_id":"athlete-1","actor_id":"coach-1",
        "payload":{"metric":"technical_quality","threshold":8,"action":"PROGRESS","adjustment":1},
        "coach_final_authority":True,"execution_authorized":False})
    assert r.status_code==201

    r=client.post("/api/v1/features/feat-031/drill-library",json={
        "subject_id":"drill-1","actor_id":"coach-1",
        "payload":{"drill_id":"D1","name":"Uchi-komi","judo_area":"Nage-waza",
        "technical_skill":"Seoi-nage entry","problem_target":"late entry",
        "decision_target":"entry timing","age_suitability":"U11+","skill_level":"intermediate",
        "execution_pattern":"controlled repetitions","kpi":"entry quality",
        "safety_constraints":"coach supervised"},
        "evidence_refs":["REF-015"],"coach_final_authority":True,"execution_authorized":False})
    assert r.status_code==201


def test_semantic_validation_rejects_invalid_feature_shapes():
    bad = client.post("/api/v1/features/feat-069/competition-trend-analysis", json={
        "subject_id":"athlete-1","actor_id":"coach-1",
        "payload":{"athlete_id":"athlete-1","event_ids":["E1"],"trend":"up"},
        "evidence_refs":["REF-015"],"coach_final_authority":True,"execution_authorized":False})
    assert bad.status_code == 400
    assert "two events" in str(bad.json()["detail"])

    bad = client.post("/api/v1/features/feat-075/approved-data-reporting-export", json={
        "subject_id":"report-1","actor_id":"coach-1",
        "payload":{"report_id":"R1","approved_record_ids":["A1"],"format":"XML"},
        "coach_final_authority":True,"execution_authorized":False})
    assert bad.status_code == 400
    assert "format" in str(bad.json()["detail"])

    bad = client.post("/api/v1/features/feat-039/progress-state-update", json={
        "subject_id":"athlete-1","actor_id":"coach-1",
        "payload":{"athlete_id":"athlete-1","state":"GUESS","state_basis":"unsupported"},
        "evidence_refs":["REF-015"],"coach_final_authority":True,"execution_authorized":False})
    assert bad.status_code == 400
