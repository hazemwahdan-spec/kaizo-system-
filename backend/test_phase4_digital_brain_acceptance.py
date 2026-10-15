"""Phase 4 Digital Brain integration acceptance across existing governed APIs.

These tests intentionally reuse existing contracts. They do not certify production
readiness; the workflow runs against ephemeral PostgreSQL in CI.
"""
import os
import uuid

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/kaizo_test"

from fastapi.testclient import TestClient
import main
import persistence

persistence.initialize()
client = TestClient(main.app)


def post(path, payload, expected=(200, 201)):
    response = client.post(path, json=payload)
    assert response.status_code in expected, (path, response.status_code, response.text)
    return response.json()


def build_governed_decision():
    suffix = uuid.uuid4().hex[:10]
    coach_id = f"phase4-coach-{suffix}"
    athlete = post("/api/v1/athletes", {"display_name": f"Phase4 Athlete {suffix}"})
    assessment = post("/api/v1/assessments", {
        "athlete_id": athlete["athlete_id"],
        "template_id": "P4-BASELINE",
        "measurements": {"entry_timing_score": 4},
        "recorded_by": coach_id,
    })
    problem = post("/api/v1/problem-statements", {
        "athlete_id": athlete["athlete_id"],
        "assessment_id": assessment["assessment_id"],
        "statement": "Entry timing deteriorates under resistance",
        "problem_type": "TECHNICAL",
        "created_by": coach_id,
    })
    evidence = post("/api/v1/evidence", {
        "evidence_id": f"P4-EVID-{suffix}",
        "subject_type": "problem",
        "subject_id": problem["problem_id"],
        "evidence_level": "E2",
        "status": "VERIFIED",
        "source_ref": "PHASE4-INTEGRATION-TEST",
        "claim": "Entry timing score recorded at baseline",
        "observed_value": {"entry_timing_score": 4},
        "verified_by": coach_id,
    })
    diagnosis = post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", {
        "problem_id": problem["problem_id"],
        "evidence_ids": [evidence["evidence_id"]],
        "diagnosis": "Timing decision under resistance",
        "diagnosed_by": coach_id,
    })
    generated = post(
        f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates",
        {"diagnosis_id": diagnosis["diagnosis_id"], "requested_by": coach_id},
    )
    candidate = generated["candidates"][0]
    assert generated["coach_review_required"] is True
    assert candidate["status"] == "PENDING_COACH_REVIEW"

    rationale = post(
        f"/api/v1/decision-candidates/{candidate['candidate_id']}/rationale",
        {
            "candidate_id": candidate["candidate_id"],
            "rationale": "Candidate is linked to the observed baseline evidence.",
            "evidence_ids": [evidence["evidence_id"]],
            "recorded_by": coach_id,
        },
    )
    assert rationale["coach_review_required"] is True

    review = post(
        f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review",
        {
            "candidate_id": candidate["candidate_id"],
            "action": "CONFIRM",
            "coach_id": coach_id,
        },
    )
    assert review["status"] == "COACH_CONFIRMED"
    assert review["coach_final_authority"] is True
    assert review["execution_authorized"] is False

    decision = post(
        f"/api/v1/decision-candidates/{candidate['candidate_id']}/decision-record",
        {
            "candidate_id": candidate["candidate_id"],
            "coach_id": coach_id,
            "outcome_intent": "Improve entry timing under resistance",
        },
    )
    assert decision["status"] == "RECORDED"
    assert decision["coach_action"] == "CONFIRM"
    assert decision["coach_final_authority"] is True
    assert decision["execution_authorized"] is False

    plan = post("/api/v1/training-plans", {
        "athlete_id": athlete["athlete_id"],
        "decision_id": decision["decision_id"],
        "title": "Phase 4 evidence-linked draft plan",
        "objective": "Improve entry timing under resistance",
        "created_by": coach_id,
        "constraints": {"duration_min": 60},
    })
    return {
        "athlete": athlete,
        "evidence": evidence,
        "candidate": candidate,
        "decision": decision,
        "plan": plan,
        "coach_id": coach_id,
    }


def test_phase4_decision_to_plan_preserves_evidence_and_coach_authority():
    result = build_governed_decision()
    plan = result["plan"]
    assert plan["status"] == "DRAFT"
    assert plan["coach_final_authority"] is True
    assert plan["execution_authorized"] is False

    readback = client.get(f"/api/v1/training-plans/{plan['plan_id']}")
    assert readback.status_code == 200
    assert readback.json()["plan_id"] == plan["plan_id"]
    assert readback.json()["execution_authorized"] is False

    # Public audit-log access remains fail-closed without authenticated
    # tenant authorization. Validate emitted events through the internal spine.
    audit = client.get("/api/v1/audit/logs")
    assert audit.status_code == 503
    actions = [item.get("action") for item in main.AUDIT_LOGS]
    assert "DECISION_CANDIDATES_GENERATED" in actions
    assert any("DECISION" in (action or "") for action in actions)


def test_phase4_evidence_safety_fails_closed_without_coach_authority():
    response = client.post("/api/v1/evidence-safety/feat-059/block", json={
        "action_id": "P4-UNAUTHORIZED-ACTION",
        "block_reason": "Required coach authority was not granted",
        "diagnostic": {"test": "phase4-negative-path"},
        "evidence_refs": ["P4-NEGATIVE-TEST"],
        "blocked_by": "phase4-test",
        "coach_final_authority": False,
    })
    assert response.status_code == 409
    assert "Coach Final Authority" in response.text


if __name__ == "__main__":
    test_phase4_decision_to_plan_preserves_evidence_and_coach_authority()
    test_phase4_evidence_safety_fails_closed_without_coach_authority()
    print("Phase 4 Digital Brain integration acceptance passed")
