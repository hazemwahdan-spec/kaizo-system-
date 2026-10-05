"""Acceptance tests for FEAT-024 coach confirm/override."""

import os
import uuid

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/kaizo_test"

from fastapi.testclient import TestClient
import main
import persistence

persistence.initialize()
client = TestClient(main.app)


def post(path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in (200, 201), (response.status_code, response.text)
    return response.json()


def build_candidate():
    suffix = uuid.uuid4().hex[:8]
    athlete = post("/api/v1/athletes", {"display_name": f"FEAT024 Athlete {suffix}"})
    assessment = post("/api/v1/assessments", {
        "athlete_id": athlete["athlete_id"],
        "template_id": "FEAT-024-TEMPLATE",
        "measurements": {"score": 4},
        "recorded_by": "coach-feat024",
    })
    problem = post("/api/v1/problem-statements", {
        "athlete_id": athlete["athlete_id"],
        "assessment_id": assessment["assessment_id"],
        "statement": "Coach review test problem",
        "problem_type": "TECHNICAL",
        "created_by": "coach-feat024",
    })
    evidence = post("/api/v1/evidence", {
        "evidence_id": f"FEAT024-EVID-{suffix}",
        "subject_type": "problem",
        "subject_id": problem["problem_id"],
        "evidence_level": "E2",
        "status": "VERIFIED",
        "source_ref": "FEAT-024-TEST",
        "claim": "Observed decision evidence",
        "observed_value": {"score": 4},
        "verified_by": "coach-feat024",
    })
    diagnosis = post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", {
        "problem_id": problem["problem_id"],
        "evidence_ids": [evidence["evidence_id"]],
        "diagnosis": "Coach review test diagnosis",
        "diagnosed_by": "coach-feat024",
    })
    generated = post(f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates", {
        "diagnosis_id": diagnosis["diagnosis_id"],
        "requested_by": "coach-feat024",
    })
    return generated["candidates"][0]


def test_coach_confirm_is_explicit_and_not_autonomous():
    candidate = build_candidate()
    review = post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review", {
        "candidate_id": candidate["candidate_id"],
        "action": "CONFIRM",
        "coach_id": "coach-feat024",
    })
    assert review["action"] == "CONFIRM"
    assert review["status"] == "COACH_CONFIRMED"
    assert review["coach_final_authority"] is True
    assert review["execution_authorized"] is False

    readback = client.get(f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review")
    assert readback.status_code == 200
    body = readback.json()
    assert any(item["review_id"] == review["review_id"] for item in body["reviews"])
    assert body["execution_authorized"] is False


def test_coach_override_requires_reason_and_is_recorded():
    candidate = build_candidate()
    missing = client.post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review", json={
        "candidate_id": candidate["candidate_id"],
        "action": "OVERRIDE",
        "coach_id": "coach-feat024",
    })
    assert missing.status_code == 400

    review = post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review", {
        "candidate_id": candidate["candidate_id"],
        "action": "OVERRIDE",
        "coach_id": "coach-feat024",
        "override_reason": "Coach selected a different training response based on live context.",
    })
    assert review["action"] == "OVERRIDE"
    assert review["status"] == "COACH_OVERRIDDEN"
    assert review["override_reason"]
    assert review["coach_final_authority"] is True
    assert review["execution_authorized"] is False


if __name__ == "__main__":
    test_coach_confirm_is_explicit_and_not_autonomous()
    test_coach_override_requires_reason_and_is_recorded()
    print("FEAT-024 acceptance tests passed")
