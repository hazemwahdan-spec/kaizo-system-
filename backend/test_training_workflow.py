"""Acceptance tests for FEAT-033..040 end-to-end workflow semantics."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from training_workflow import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)


def test_033_to_040_create_real_feature_records():
    cases = [
        ("/api/v1/training-workflow/feat-033/decision-drill",
         {"athlete_id":"A1","decision_id":"D1","drill_id":"DR1","rationale":"Targets entry timing",
          "evidence_refs":["REF-015"],"selected_by":"coach"}),
        ("/api/v1/training-workflow/feat-034/drill-prescription",
         {"athlete_id":"A1","decision_id":"D1","session_id":"S1","drill_id":"DR1",
          "objective":"Improve entry timing","dosage":{"sets":3,"reps":5},
          "prescribed_by":"coach"}),
        ("/api/v1/training-workflow/feat-035/execution-cues",
         {"athlete_id":"A1","session_id":"S1","drill_id":"DR1",
          "cues":["Elbow close","Enter under balance"],"checklist":["Grip secured","Posture stable"],
          "created_by":"coach"}),
        ("/api/v1/training-workflow/feat-036/training-response",
         {"athlete_id":"A1","session_id":"S1","response":{"quality":"GOOD"},
          "kpi_values":{"entry_success":4},"observed_by":"coach"}),
        ("/api/v1/training-workflow/feat-037/retest",
         {"athlete_id":"A1","session_id":"S1","baseline_reference":"BASE-1",
          "retest_values":{"entry_success":6},"evidence_refs":["REF-016"],"retested_by":"coach"}),
        ("/api/v1/training-workflow/feat-038/before-after",
         {"athlete_id":"A1","baseline":{"entry_success":4},"current":{"entry_success":6},
          "comparison_method":"absolute_change","compared_by":"coach"}),
        ("/api/v1/training-workflow/feat-039/progress-state",
         {"athlete_id":"A1","state":{"status":"IMPROVING","entry_success":6},
          "evidence_refs":["REF-016"],"updated_by":"coach"}),
        ("/api/v1/training-workflow/feat-040/next-decision-trigger",
         {"athlete_id":"A1","session_id":"S1","trigger_type":"RETEST_COMPLETE",
          "trigger_reason":"Retest changed the decision state","required_evidence":["REF-016"],
          "created_by":"coach"}),
    ]
    for path, payload in cases:
        response = client.post(path, json=payload)
        assert response.status_code == 201, (path, response.text)
        body = response.json()
        assert body["feature_id"].lower() in path
        assert body["coach_final_authority"] is True
        assert body["execution_authorized"] is False


def test_authority_and_fail_closed_guards():
    payload = {
        "athlete_id":"A1","decision_id":"D1","drill_id":"DR1",
        "rationale":"x","evidence_refs":["REF-015"],"selected_by":"coach",
        "coach_final_authority":False
    }
    response = client.post(
        "/api/v1/training-workflow/feat-033/decision-drill", json=payload
    )
    assert response.status_code == 400

    invalid = {
        "athlete_id":"A1","decision_id":"D1","session_id":"S1","drill_id":"DR1",
        "objective":"x","dosage":{"sets":0,"reps":5},"prescribed_by":"coach"
    }
    response = client.post(
        "/api/v1/training-workflow/feat-034/drill-prescription", json=invalid
    )
    assert response.status_code == 400
