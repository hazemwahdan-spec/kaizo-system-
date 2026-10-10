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
    detail=str(r.json()["detail"])
    assert "evidence" in detail.lower()
    assert "at least one evidence reference is required" in detail.lower()

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

def test_competition_event_readiness_and_coach_authority_acceptance():
    denied = client.post("/api/v1/competition/events", json={
        "event_name": "Judo Open", "date": "2026-11-12",
        "context": {"division": "U15"}, "created_by": "coach-test",
        "coach_final_authority": False,
    })
    assert denied.status_code == 409
    assert denied.json()["detail"] == "COACH_FINAL_AUTHORITY_REQUIRED"

    created = client.post("/api/v1/competition/events", json={
        "event_name": "KAIZO Acceptance Event", "date": "2026-11-12",
        "context": {"division": "U15", "purpose": "acceptance-test"},
        "created_by": "coach-test", "evidence_refs": ["REF-TEST-001"],
        "coach_final_authority": True,
    })
    assert created.status_code == 201
    event = created.json()
    assert event["coach_final_authority"] is True
    assert event["execution_authorized"] is False
    assert client.get(f"/api/v1/competition/events/{event['event_id']}").status_code == 200

    readiness = client.post("/api/v1/competition/readiness", json={
        "athlete_id": "athlete-test-001", "event_id": event["event_id"],
        "indicators": {"kumi_kata": "medium", "randori": "medium"},
        "assessed_by": "coach-test", "evidence_refs": ["REF-TEST-002"],
        "coach_final_authority": True,
    })
    assert readiness.status_code == 201
    assert readiness.json()["execution_authorized"] is False
    readback = client.get(f"/api/v1/competition/readiness/athlete-test-001/{event['event_id']}")
    assert readback.status_code == 200
    assert readback.json()["indicators"]["kumi_kata"] == "medium"


def test_competition_performance_trend_requires_two_evidence_events():
    event_ids = []
    for label in ("A", "B"):
        r = client.post("/api/v1/competition/events", json={
            "event_name": f"Trend Test {label}", "date": "2026-11-12",
            "context": {"test": "trend"}, "created_by": "coach-test",
            "coach_final_authority": True,
        })
        assert r.status_code == 201
        event_ids.append(r.json()["event_id"])
    for event_id, score in zip(event_ids, (5, 8)):
        r = client.post("/api/v1/competition/performance", json={
            "athlete_id": "athlete-trend-test", "event_id": event_id,
            "performance": {"score": score}, "recorded_by": "coach-test",
            "evidence_refs": ["REF-TREND-TEST"], "coach_final_authority": True,
        })
        assert r.status_code == 201
        assert r.json()["execution_authorized"] is False
    trend = client.get(
        f"/api/v1/competition/trend/athlete-trend-test?event_ids={event_ids[0]},{event_ids[1]}"
    )
    assert trend.status_code == 200
    assert trend.json()["scores"] == [5.0, 8.0]
    assert trend.json()["trend"] == "IMPROVING"
    assert trend.json()["execution_authorized"] is False


def test_academy_membership_assignment_and_dashboard_acceptance():
    denied = client.post("/api/v1/academy/academies", json={
        "name": "Denied Academy Test", "owner_id": "owner-test",
        "coach_final_authority": False,
    })
    assert denied.status_code == 409

    created = client.post("/api/v1/academy/academies", json={
        "name": "KAIZO Academy Acceptance Test", "owner_id": "owner-test",
        "coach_final_authority": True,
    })
    assert created.status_code == 201
    academy = created.json()
    academy_id = academy["academy_id"]
    assert academy["execution_authorized"] is False

    missing_member = client.post("/api/v1/academy/assignments", json={
        "academy_id": academy_id, "athlete_id": "athlete-academy-test",
        "coach_ids": ["coach-not-member"], "coach_final_authority": True,
    })
    assert missing_member.status_code == 409
    assert "membership required" in missing_member.json()["detail"]

    for coach_id in ("coach-a-test", "coach-b-test"):
        member = client.post("/api/v1/academy/memberships", json={
            "academy_id": academy_id, "coach_id": coach_id, "role": "COACH",
            "coach_final_authority": True,
        })
        assert member.status_code == 201
    group = client.post("/api/v1/academy/groups", json={
        "academy_id": academy_id, "name": "U15 Acceptance Group",
        "coach_final_authority": True,
    })
    assert group.status_code == 201
    assignment = client.post("/api/v1/academy/assignments", json={
        "academy_id": academy_id, "athlete_id": "athlete-academy-test",
        "coach_ids": ["coach-a-test", "coach-b-test"],
        "coach_final_authority": True,
    })
    assert assignment.status_code == 201
    assert len(assignment.json()["coach_ids"]) == 2
    assert assignment.json()["execution_authorized"] is False

    dashboard = client.get(f"/api/v1/academy/academies/{academy_id}/dashboard")
    assert dashboard.status_code == 200
    metrics = dashboard.json()["metrics"]
    assert metrics["active_coaches"] == 2
    assert metrics["active_groups"] == 1
    assert metrics["assigned_athletes"] == 1
    assert metrics["multi_coach_athletes"] == 1
    assert dashboard.json()["execution_authorized"] is False
