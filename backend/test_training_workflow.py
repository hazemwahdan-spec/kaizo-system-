"""Security regression tests for same-athlete FEAT-033..040 lineage."""
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
import training_workflow
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
         {"athlete_id": athlete_id, "decision_id": "D1", "drill_id": "DR1",
          "rationale": "Targets entry timing", "evidence_refs": ["REF-015"],
          "selected_by": "spoofed-coach"}),
        ("/api/v1/training-workflow/feat-034/drill-prescription",
         {"athlete_id": athlete_id, "decision_id": "D1", "session_id": "S1",
          "drill_id": "DR1", "selection_record_id": "SELECT-1", "objective": "Improve entry timing",
          "dosage": {"sets": 3, "reps": 5}, "prescribed_by": "spoofed-coach"}),
        ("/api/v1/training-workflow/feat-035/execution-cues",
         {"athlete_id": athlete_id, "session_id": "S1", "prescription_record_id": "PRESCRIBE-1", "drill_id": "DR1",
          "cues": ["Elbow close", "Enter under balance"],
          "checklist": ["Grip secured", "Posture stable"], "created_by": "spoofed-coach"}),
        ("/api/v1/training-workflow/feat-036/training-response",
         {"athlete_id": athlete_id, "session_id": "S1", "cue_record_id": "CUE-1",
          "response": {"quality": "GOOD"}, "kpi_values": {"entry_success": 4},
          "observed_by": "spoofed-coach"}),
        ("/api/v1/training-workflow/feat-037/retest",
         {"athlete_id": athlete_id, "session_id": "S1", "response_record_id": "RESPONSE-1", "baseline_reference": "BASE-1",
          "retest_values": {"entry_success": 6}, "evidence_refs": ["REF-016"],
          "retested_by": "spoofed-coach"}),
        ("/api/v1/training-workflow/feat-038/before-after",
         {"athlete_id": athlete_id, "baseline": {"entry_success": 4},
          "current": {"entry_success": 6}, "comparison_method": "absolute_change",
          "retest_record_id": "RETEST-1", "compared_by": "spoofed-coach"}),
        ("/api/v1/training-workflow/feat-039/progress-state",
         {"athlete_id": athlete_id, "state": {"status": "IMPROVING", "entry_success": 6},
          "evidence_refs": ["REF-016"], "comparison_record_id": "COMPARE-1",
          "updated_by": "spoofed-coach"}),
        ("/api/v1/training-workflow/feat-040/next-decision-trigger",
         {"athlete_id": athlete_id, "session_id": "S1",
          "progress_record_id": "PROGRESS-1", "trigger_type": "RETEST_COMPLETE",
          "trigger_reason": "Retest changed the decision state",
          "required_evidence": ["REF-016"], "created_by": "spoofed-coach"}),
    ]


def test_all_feat_033_to_040_reject_orphaned_decision_session_and_lineage_references():
    for path, payload in cases(ATHLETE_ID):
        response = client.post(path, json=payload, headers=COACH_HEADERS)
        assert response.status_code in (404, 409), (path, response.text)
    assert training_workflow._MEMORY_RECORDS == []
    assert training_workflow._MEMORY_AUDIT == []


def test_anonymous_and_non_coach_requests_are_denied_without_writes():
    path, payload = cases(ATHLETE_ID)[0]
    assert client.post(path, json=payload).status_code == 401
    non_coach = {**COACH_HEADERS, "X-KAIZO-Role": "athlete"}
    assert client.post(path, json=payload, headers=non_coach).status_code == 403
    assert client.get(
        f"/api/v1/training-workflow/athletes/{ATHLETE_ID}", headers=non_coach
    ).status_code == 403
    assert training_workflow._MEMORY_RECORDS == []


def test_cross_coach_and_cross_tenant_read_write_are_denied():
    path, payload = cases(ATHLETE_ID)[0]
    assert client.post(path, json=payload, headers=OTHER_COACH_HEADERS).status_code == 404
    other_tenant = {**COACH_HEADERS, "X-KAIZO-Tenant": "tenant-2"}
    assert client.post(path, json=payload, headers=other_tenant).status_code == 404
    assert client.get(
        f"/api/v1/training-workflow/athletes/{ATHLETE_ID}", headers=OTHER_COACH_HEADERS
    ).status_code == 404
    assert training_workflow._MEMORY_RECORDS == []


def test_history_is_empty_until_verified_decision_and_session_lineage_exists():
    own = client.get(
        f"/api/v1/training-workflow/athletes/{ATHLETE_ID}", headers=COACH_HEADERS
    )
    assert own.status_code == 200
    assert all(not records for records in own.json()["features"].values())
    assert client.get(
        f"/api/v1/training-workflow/athletes/{ATHLETE_ID}", headers=OTHER_COACH_HEADERS
    ).status_code == 404


def test_client_authority_boolean_is_ignored_and_invalid_dosage_is_rejected():
    path, payload = cases(ATHLETE_ID)[0]
    payload["coach_final_authority"] = False
    assert client.post(path, json=payload, headers=COACH_HEADERS).status_code == 404
    invalid = {
        "athlete_id": ATHLETE_ID, "decision_id": "D1", "session_id": "S1",
        "selection_record_id": "SELECT-1", "drill_id": "DR1",
        "objective": "x", "dosage": {"sets": 0, "reps": 5},
    }
    assert client.post(
        "/api/v1/training-workflow/feat-034/drill-prescription",
        json=invalid, headers=COACH_HEADERS,
    ).status_code == 400
    assert training_workflow._MEMORY_RECORDS == []
