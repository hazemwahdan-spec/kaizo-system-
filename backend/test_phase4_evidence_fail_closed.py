"""Phase 4 negative tests: unverified/stale/conflicting/E0 evidence must not drive diagnosis."""
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


def context():
    suffix = uuid.uuid4().hex[:8]
    coach = f"phase4-evidence-{suffix}"
    athlete = post("/api/v1/athletes", {"display_name": f"Phase4 Evidence {suffix}"})
    assessment = post("/api/v1/assessments", {
        "athlete_id": athlete["athlete_id"],
        "template_id": f"P4-EVIDENCE-{suffix}",
        "measurements": {"score": 4},
        "recorded_by": coach,
    })
    problem = post("/api/v1/problem-statements", {
        "athlete_id": athlete["athlete_id"],
        "assessment_id": assessment["assessment_id"],
        "statement": "Evidence safety decision test",
        "problem_type": "TECHNICAL",
        "created_by": coach,
    })
    return suffix, coach, problem


def create_evidence(suffix, coach, problem, status, level="E2"):
    # Seed the configured database directly as a trusted test fixture. These
    # tests target diagnosis/rationale/candidate guards, not public ingestion.
    record = {
        "evidence_id": f"P4-GUARD-{suffix}-{status}-{level}",
        "subject_type": "problem",
        "subject_id": problem["problem_id"],
        "evidence_level": level,
        "status": status,
        "source_ref": f"P4-SOURCE-{suffix}",
        "claim": "Evidence status guard test",
        "observed_value": {"score": 4},
        "verified_by": "trusted-test-fixture",
        "verified_at": "2026-10-18T00:00:00Z",
        "notes": None,
    }
    persistence.upsert_evidence(record)
    main.EVIDENCE_RECORDS[record["evidence_id"]] = record
    return record


def diagnose(problem, evidence_id, coach):
    return client.post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", json={
        "problem_id": problem["problem_id"],
        "evidence_ids": [evidence_id],
        "diagnosis": "Decision-driving diagnosis",
        "diagnosed_by": coach,
    })


def test_phase4_unverified_stale_conflicted_or_rejected_evidence_is_blocked():
    for status in ("UNVERIFIED", "STALE", "CONFLICTED", "REJECTED", "REVIEW_REQUIRED"):
        suffix, coach, problem = context()
        evidence = create_evidence(suffix, coach, problem, status)
        response = diagnose(problem, evidence["evidence_id"], coach)
        assert response.status_code == 409, (status, response.status_code, response.text)
        assert "not verified" in response.text
        assert response.json()["detail"]["decision_state"] == "HOLD"


def test_phase4_e0_cannot_drive_diagnosis_even_when_marked_verified():
    suffix, coach, problem = context()
    evidence = create_evidence(suffix, coach, problem, "verified", level="E0")
    response = diagnose(problem, evidence["evidence_id"], coach)
    assert response.status_code == 409, response.text
    assert "E0 evidence cannot drive a diagnosis" in response.text
    assert response.json()["detail"]["decision_state"] == "HOLD"


def test_phase4_public_evidence_reads_and_writes_authenticate_before_feature_gate():
    # With the feature flag unset/false, anonymous callers must still receive
    # an authorization response, not the feature's 503 activation response.
    os.environ.pop("KAIZO_EVIDENCE_PUBLISHER_ENABLED", None)
    suffix, coach, problem = context()
    for response in (
        client.get("/api/v1/evidence"),
        client.get("/api/v1/evidence/phase4-anonymous-auth-order-probe"),
        client.post("/api/v1/evidence", json={
            "evidence_id": f"P4-INVALID-STATUS-{suffix}",
            "subject_type": "problem",
            "subject_id": problem["problem_id"],
            "evidence_level": "E2",
            "status": "TRUST_ME",
            "source_ref": "P4-INVALID-SOURCE",
            "claim": "Anonymous ingestion must fail closed",
            "observed_value": {"score": 4},
            "verified_by": coach,
        }),
    ):
        assert response.status_code == 401, (response.status_code, response.text)
        assert "publisher identity" in response.text.lower() or "verified oidc identity" in response.text.lower()


def candidate_context():
    suffix, coach, problem = context()
    evidence = create_evidence(suffix, coach, problem, "VERIFIED", level="E2")
    diagnosis = post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", {
        "problem_id": problem["problem_id"],
        "evidence_ids": [evidence["evidence_id"]],
        "diagnosis": "Verified control diagnosis",
        "diagnosed_by": coach,
    })
    candidate = post(f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates", {
        "diagnosis_id": diagnosis["diagnosis_id"],
        "requested_by": coach,
    })["candidates"][0]
    return suffix, coach, problem, candidate


def test_phase4_unverified_and_e0_evidence_cannot_support_decision_rationale():
    suffix, coach, problem, candidate = candidate_context()
    unverified = create_evidence(suffix, coach, problem, "UNVERIFIED", level="E2")
    response = client.post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/rationale", json={
        "candidate_id": candidate["candidate_id"],
        "rationale": "Must not cite unverified evidence",
        "evidence_ids": [unverified["evidence_id"]],
        "recorded_by": coach,
    })
    assert response.status_code == 409, response.text
    assert "evidence is not verified" in response.text
    assert response.json()["detail"]["decision_state"] == "HOLD"

    suffix, coach, problem, candidate = candidate_context()
    e0 = create_evidence(suffix, coach, problem, "VERIFIED", level="E0")
    response = client.post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/rationale", json={
        "candidate_id": candidate["candidate_id"],
        "rationale": "Must not cite E0 as decision support",
        "evidence_ids": [e0["evidence_id"]],
        "recorded_by": coach,
    })
    assert response.status_code == 409, response.text
    assert "E0 evidence cannot support a decision rationale" in response.text
    assert response.json()["detail"]["decision_state"] == "HOLD"


def test_phase4_missing_evidence_returns_explicit_hold_reason():
    suffix, coach, problem = context()
    response = client.post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", json={
        "problem_id": problem["problem_id"],
        "evidence_ids": [],
        "diagnosis": "Missing evidence must hold",
        "diagnosed_by": coach,
    })
    assert response.status_code == 400
    assert response.json()["detail"]["decision_state"] == "HOLD"
    assert "at least one evidence_id is required" in response.text

    suffix, coach, problem, candidate = candidate_context()
    rationale = client.post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/rationale", json={
        "candidate_id": candidate["candidate_id"],
        "rationale": "Missing evidence must hold",
        "evidence_ids": [],
        "recorded_by": coach,
    })
    assert rationale.status_code == 400
    assert rationale.json()["detail"]["decision_state"] == "HOLD"


def test_phase4_candidate_generation_revalidates_legacy_or_changed_evidence():
    for changed_field, changed_value, expected_reason in (
        ("status", "STALE", "evidence is not verified"),
        ("evidence_level", "E0", "E0 evidence cannot drive decision candidates"),
    ):
        suffix, coach, problem = context()
        evidence = create_evidence(suffix, coach, problem, "VERIFIED", level="E2")
        diagnosis = post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", {
            "problem_id": problem["problem_id"],
            "evidence_ids": [evidence["evidence_id"]],
            "diagnosis": "Initially verified diagnosis",
            "diagnosed_by": coach,
        })
        evidence[changed_field] = changed_value
        persistence.upsert_evidence(evidence)

        response = client.post(
            f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates",
            json={"diagnosis_id": diagnosis["diagnosis_id"], "requested_by": coach},
        )
        assert response.status_code == 409, response.text
        assert response.json()["detail"]["decision_state"] == "HOLD"
        assert expected_reason in response.text


if __name__ == "__main__":
    test_phase4_unverified_stale_conflicted_or_rejected_evidence_is_blocked()
    test_phase4_e0_cannot_drive_diagnosis_even_when_marked_verified()
    test_phase4_public_evidence_reads_and_writes_authenticate_before_feature_gate()
    test_phase4_unverified_and_e0_evidence_cannot_support_decision_rationale()
    test_phase4_missing_evidence_returns_explicit_hold_reason()
    test_phase4_candidate_generation_revalidates_legacy_or_changed_evidence()
    print("Phase 4 evidence fail-closed acceptance passed")
