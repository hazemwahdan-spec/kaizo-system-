"""Security regression tests for ownership-scoped FEAT-033..040 workflows."""
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
os.environ["KAIZO_IDENTITY_MODE"] = "development"
os.environ["KAIZO_PERSISTENCE_MODE"] = "memory"

import persistence
from productization import coach_roster
from training_workflow import router, reset_memory_state

app = FastAPI()
app.include_router(router)
client = TestClient(app)

COACH_HEADERS = {
    "X-KAIZO-Actor": "coach-1",
    "X-KAIZO-Role": "coach",
    "X-KAIZO-Tenant": "tenant-1",
}
OTHER_COACH_HEADERS = {
    "X-KAIZO-Actor": "coach-2",
    "X-KAIZO-Role": "coach",
    "X-KAIZO-Tenant": "tenant-1",
}


def setup_function():
    reset_memory_state()
    coach_roster.reset_memory_state()
    global ATHLETE_ID
    athlete = coach_roster.create_owned_athlete(
        tenant_id="tenant-1", coach_actor_id="coach-1",
        display_name="Owned athlete for workflow tests",
    )
    ATHLETE_ID = athlete["athlete_id"]


def cases(athlete_id):
    return [
        ("/api/v1/training-workflow/feat-033/decision-drill",
         {"athlete_id":athlete_id,"decision_id":"D1","drill_id":"DR1","rationale":"Targets entry timing",
          "evidence_refs":["REF-015"],"selected_by":"spoofed-coach"}),
        ("/api/v1/training-workflow/feat-034/drill-prescription",
         {"athlete_id":athlete_id,"decision_id":"D1","session_id":"S1","drill_id":"DR1",
          "objective":"Improve entry timing","dosage":{"sets":3,"reps":5},"prescribed_by":"spoofed-coach"}),
        ("/api/v1/training-workflow/feat-035/execution-cues",
         {"athlete_id":athlete_id,"session_id":"S1","drill_id":"DR1",
          "cues":["Elbow close","Enter under balance"],"checklist":["Grip secured","Posture stable"],
          "created_by":"spoofed-coach"}),
        ("/api/v1/training-workflow/feat-036/training-response",
         {"athlete_id":athlete_id,"session_id":"S1","response":{"quality":"GOOD"},
          "drill_id":"DR1","prescription_record_id":"PENDING-034","execution_cue_record_id":"PENDING-035","kpi_values":{"entry_success":4},"observed_by":"spoofed-coach"}),
        ("/api/v1/training-workflow/feat-037/retest",
         {"athlete_id":athlete_id,"session_id":"S1","response_record_id":"PENDING-036","baseline_reference":"FEAT-036",
          "retest_values":{"entry_success":6},"evidence_refs":["REF-016"],"retested_by":"spoofed-coach"}),
        ("/api/v1/training-workflow/feat-038/before-after",
         {"athlete_id":athlete_id,"response_record_id":"PENDING-036","retest_record_id":"PENDING-037","baseline":{"entry_success":4},"current":{"entry_success":6},
          "comparison_method":"absolute_change","compared_by":"spoofed-coach"}),
        ("/api/v1/training-workflow/feat-039/progress-state",
         {"athlete_id":athlete_id,"comparison_record_id":"PENDING-038","state":{"status":"IMPROVING","entry_success":6},
          "evidence_refs":["REF-016"],"updated_by":"spoofed-coach"}),
        ("/api/v1/training-workflow/feat-040/next-decision-trigger",
         {"athlete_id":athlete_id,"session_id":"S1","progress_record_id":"PENDING-039","trigger_type":"RETEST_COMPLETE",
          "trigger_reason":"Retest changed the decision state","required_evidence":["REF-016"],
          "created_by":"spoofed-coach"}),
    ]


def test_all_feat_033_to_040_writes_require_owned_coach_and_attribute_verified_actor():
    records = {}
    for path, original in cases(ATHLETE_ID):
        payload = dict(original)
        feature = path.split("/feat-")[1][:3]
        if feature == "036":
            payload["prescription_record_id"] = records["034"]["record_id"]
            payload["execution_cue_record_id"] = records["035"]["record_id"]
        elif feature == "037":
            payload["response_record_id"] = records["036"]["record_id"]
        elif feature == "038":
            payload["response_record_id"] = records["036"]["record_id"]
            payload["retest_record_id"] = records["037"]["record_id"]
        elif feature == "039":
            payload["comparison_record_id"] = records["038"]["record_id"]
        elif feature == "040":
            payload["progress_record_id"] = records["039"]["record_id"]
        response = client.post(path, json=payload, headers=COACH_HEADERS)
        assert response.status_code == 201, (path, response.text)
        body = response.json()
        records[feature] = body
        assert body["created_by"] == "coach-1"
        assert body["coach_actor_id"] == "coach-1"
        assert body["tenant_id"] == "tenant-1"
        assert body["coach_final_authority"] is True
        assert body["execution_authorized"] is False


def test_anonymous_and_non_coach_requests_are_denied_without_writes():
    path, payload = cases(ATHLETE_ID)[0]
    assert client.post(path, json=payload).status_code == 401
    non_coach = {**COACH_HEADERS, "X-KAIZO-Role":"athlete"}
    assert client.post(path, json=payload, headers=non_coach).status_code == 403
    assert client.get(f"/api/v1/training-workflow/athletes/{ATHLETE_ID}", headers=non_coach).status_code == 403


def test_cross_coach_and_cross_tenant_read_write_are_denied():
    path, payload = cases(ATHLETE_ID)[0]
    assert client.post(path, json=payload, headers=OTHER_COACH_HEADERS).status_code == 404
    other_tenant = {**COACH_HEADERS, "X-KAIZO-Tenant":"tenant-2"}
    assert client.post(path, json=payload, headers=other_tenant).status_code == 404
    assert client.get(f"/api/v1/training-workflow/athletes/{ATHLETE_ID}", headers=OTHER_COACH_HEADERS).status_code == 404


def test_workflow_history_is_scoped_and_actor_fields_cannot_be_spoofed():
    path, payload = cases(ATHLETE_ID)[0]
    assert client.post(path, json=payload, headers=COACH_HEADERS).status_code == 201
    own = client.get(f"/api/v1/training-workflow/athletes/{ATHLETE_ID}", headers=COACH_HEADERS)
    assert own.status_code == 200
    assert len(own.json()["features"]["FEAT-033"]) == 1
    assert own.json()["features"]["FEAT-033"][0]["created_by"] == "coach-1"
    assert client.get(f"/api/v1/training-workflow/athletes/{ATHLETE_ID}", headers=OTHER_COACH_HEADERS).status_code == 404


def test_invalid_training_values_and_coach_final_authority_still_fail_closed():
    path, payload = cases(ATHLETE_ID)[0]
    payload["coach_final_authority"] = False
    assert client.post(path, json=payload, headers=COACH_HEADERS).status_code == 400
    first_path, first_payload = cases(ATHLETE_ID)[0]
    assert client.post(first_path, json=first_payload, headers=COACH_HEADERS).status_code == 201
    invalid = {
        "athlete_id":ATHLETE_ID,"decision_id":"D1","session_id":"S1","drill_id":"DR1",
        "objective":"x","dosage":{"sets":0,"reps":5},
    }
    assert client.post(
        "/api/v1/training-workflow/feat-034/drill-prescription",
        json=invalid, headers=COACH_HEADERS,
    ).status_code == 400


def test_workflow_rejects_missing_predecessor():
    path, payload = cases(ATHLETE_ID)[1]
    assert client.post(path, json=payload, headers=COACH_HEADERS).status_code == 409


def test_openapi_publishes_all_feat_033_to_040_routes_and_lineage_fields():
    schema = client.get("/openapi.json").json()
    expected = {
        "/api/v1/training-workflow/feat-033/decision-drill",
        "/api/v1/training-workflow/feat-034/drill-prescription",
        "/api/v1/training-workflow/feat-035/execution-cues",
        "/api/v1/training-workflow/feat-036/training-response",
        "/api/v1/training-workflow/feat-037/retest",
        "/api/v1/training-workflow/feat-038/before-after",
        "/api/v1/training-workflow/feat-039/progress-state",
        "/api/v1/training-workflow/feat-040/next-decision-trigger",
        "/api/v1/training-workflow/athletes/{athlete_id}",
    }
    assert expected.issubset(set(schema["paths"]))
    required = {
        "ResponseRequest": {"drill_id", "prescription_record_id", "execution_cue_record_id"},
        "RetestRequest": {"response_record_id"},
        "ComparisonRequest": {"response_record_id", "retest_record_id"},
        "ProgressRequest": {"comparison_record_id"},
        "NextDecisionRequest": {"progress_record_id"},
    }
    schemas = schema["components"]["schemas"]
    for model, fields in required.items():
        assert fields.issubset(set(schemas[model]["required"]))
