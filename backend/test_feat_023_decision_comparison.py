"""Acceptance tests for FEAT-023 alternative decision comparison."""

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


def test_alternative_decision_comparison():
    suffix = uuid.uuid4().hex[:8]
    athlete = post("/api/v1/athletes", {"display_name": f"FEAT023 Athlete {suffix}"})
    assessment = post("/api/v1/assessments", {
        "athlete_id": athlete["athlete_id"],
        "template_id": "FEAT-023-TEMPLATE",
        "measurements": {"score": 4},
        "recorded_by": "coach-feat023",
    })
    problem = post("/api/v1/problem-statements", {
        "athlete_id": athlete["athlete_id"],
        "assessment_id": assessment["assessment_id"],
        "statement": "Decision comparison test problem",
        "problem_type": "TECHNICAL",
        "created_by": "coach-feat023",
    })
    evidence = post("/api/v1/evidence", {
        "subject_type": "problem",
        "subject_id": problem["problem_id"],
        "evidence_level": "E2",
        "status": "VERIFIED",
        "source_ref": "FEAT-023-TEST",
        "claim": "Observed decision evidence",
        "observed_value": {"score": 4},
        "verified_by": "coach-feat023",
        "verified_at": "2026-10-06T00:00:00",
    })
    diagnosis = post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", {
        "problem_id": problem["problem_id"],
        "evidence_ids": [evidence["evidence_id"]],
        "diagnosis": "Comparison test diagnosis",
        "diagnosed_by": "coach-feat023",
    })
    generated = post(f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates", {
        "diagnosis_id": diagnosis["diagnosis_id"],
        "requested_by": "coach-feat023",
    })
    candidate_ids = [item["candidate_id"] for item in generated["candidates"][:2]]

    comparison = post(f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-comparisons", {
        "diagnosis_id": diagnosis["diagnosis_id"],
        "candidate_ids": candidate_ids,
        "compared_by": "coach-feat023",
    })

    assert comparison["diagnosis_id"] == diagnosis["diagnosis_id"]
    assert comparison["candidate_ids"] == candidate_ids
    assert comparison["comparison_status"] == "READY_FOR_COACH_REVIEW"
    assert comparison["coach_review_required"] is True
    assert len(comparison["alternatives"]) == 2
    assert all(item["candidate_id"] in candidate_ids for item in comparison["alternatives"])

    readback = client.get(f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-comparisons")
    assert readback.status_code == 200
    body = readback.json()
    assert body["total"] >= 1
    assert any(item["comparison_id"] == comparison["comparison_id"] for item in body["comparisons"])


def test_comparison_requires_distinct_candidates():
    diagnosis_id = "missing-diagnosis"
    response = client.post(f"/api/v1/diagnoses/{diagnosis_id}/decision-comparisons", json={
        "diagnosis_id": diagnosis_id,
        "candidate_ids": ["same", "same"],
        "compared_by": "coach-feat023",
    })
    assert response.status_code == 400


if __name__ == "__main__":
    test_alternative_decision_comparison()
    test_comparison_requires_distinct_candidates()
    print("FEAT-023 acceptance tests passed")
