"""Phase 4 audit read-only and plan ownership/authority acceptance."""
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
    if path == "/api/v1/evidence":
        # Trusted test fixture: keep the public evidence API fail-closed while
        # preserving domain-level decision/audit acceptance coverage.
        record = dict(payload)
        record.setdefault("source_ref", "trusted-test-fixture")
        record.setdefault("verified_at", "2026-10-18T00:00:00Z")
        record.setdefault("notes", None)
        record["verified_by"] = "trusted-test-fixture"
        persistence.upsert_evidence(record)
        main.EVIDENCE_RECORDS[record["evidence_id"]] = record
        return record
    response = client.post(path, json=payload)
    assert response.status_code in expected, (path, response.status_code, response.text)
    return response.json()


def governed_decision():
    suffix = uuid.uuid4().hex[:8]
    coach = f"phase4-audit-{suffix}"
    athlete = post("/api/v1/athletes", {"display_name": f"P4 Audit Athlete {suffix}"})
    assessment = post("/api/v1/assessments", {
        "athlete_id": athlete["athlete_id"], "template_id": f"P4-AUDIT-{suffix}",
        "measurements": {"score": 5}, "recorded_by": coach,
    })
    problem = post("/api/v1/problem-statements", {
        "athlete_id": athlete["athlete_id"], "assessment_id": assessment["assessment_id"],
        "statement": "Audit and plan authority test", "problem_type": "TECHNICAL", "created_by": coach,
    })
    evidence = post("/api/v1/evidence", {
        "evidence_id": f"P4-AUDIT-EVID-{suffix}", "subject_type": "assessment",
        "subject_id": assessment["assessment_id"], "evidence_level": "E2", "status": "VERIFIED",
        "source_ref": "P4-AUDIT-SOURCE", "claim": "Recorded baseline", "observed_value": {"score": 5},
        "verified_by": coach,
    })
    diagnosis = post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", {
        "problem_id": problem["problem_id"], "evidence_ids": [evidence["evidence_id"]],
        "diagnosis": "Audit trace diagnosis", "diagnosed_by": coach,
    })
    candidate = post(f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates", {
        "diagnosis_id": diagnosis["diagnosis_id"], "requested_by": coach,
    })["candidates"][0]
    review = post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review", {
        "candidate_id": candidate["candidate_id"], "action": "CONFIRM", "coach_id": coach,
    })
    decision = post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/decision-record", {
        "candidate_id": candidate["candidate_id"], "coach_id": coach,
        "outcome_intent": "Retain decision provenance for audit",
    })
    return coach, athlete, assessment, candidate, review, decision


def test_phase4_audit_log_is_read_only_and_preserves_decision_events():
    _, _, _, candidate, review, decision = governed_decision()
    routes = [route for route in main.app.routes if getattr(route, "path", None) == "/api/v1/audit/logs"]
    assert len(routes) == 1
    assert routes[0].methods == {"GET"}

    for method in ("PUT", "PATCH", "DELETE"):
        response = client.request(method, "/api/v1/audit/logs", json={"action": "tamper"})
        assert response.status_code in (404, 405), (response.status_code, response.text)

    # Public audit-log access must fail closed without authenticated tenant
    # authorization. Verify the emitted events through the internal audit spine.
    response = client.get("/api/v1/audit/logs")
    assert response.status_code == 401
    logs = main.AUDIT_LOGS
    override_or_confirm = [
        item for item in logs
        if item.get("action") == "DECISION_CANDIDATE_CONFIRMED"
        and item.get("new_value", {}).get("review_id") == review["review_id"]
    ]
    assert override_or_confirm
    decision_events = [
        item for item in logs
        if item.get("action") == "DECISION_RECORD_RECORDED"
        and item.get("new_value", {}).get("decision_id") == decision["decision_id"]
    ]
    assert decision_events
    assert decision_events[0]["new_value"]["candidate_id"] == candidate["candidate_id"]
    assert decision_events[0]["new_value"]["execution_authorized"] is False


def test_phase4_training_plan_cannot_cross_athlete_or_enable_execution():
    _, athlete, _, _, _, decision = governed_decision()
    other = post("/api/v1/athletes", {"display_name": f"Wrong athlete {uuid.uuid4().hex[:8]}"})
    mismatch = client.post("/api/v1/training-plans", json={
        "athlete_id": other["athlete_id"],
        "decision_id": decision["decision_id"],
        "title": "Cross-athlete plan",
        "objective": "Should be rejected",
        "created_by": "phase4-audit-test",
    })
    assert mismatch.status_code == 400
    assert "athlete_id mismatch" in mismatch.text

    plan = post("/api/v1/training-plans", {
        "athlete_id": athlete["athlete_id"],
        "decision_id": decision["decision_id"],
        "title": "Governed draft",
        "objective": "Remain a proposal",
        "created_by": "phase4-audit-test",
        "execution_authorized": True,
    })
    assert plan["status"] == "DRAFT"
    assert plan["execution_authorized"] is False


if __name__ == "__main__":
    test_phase4_audit_log_is_read_only_and_preserves_decision_events()
    test_phase4_training_plan_cannot_cross_athlete_or_enable_execution()
    print("Phase 4 audit and plan authority acceptance passed")
