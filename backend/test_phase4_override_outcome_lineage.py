"""Phase 4 acceptance for coach override history and decision-to-outcome lineage."""
import os
import uuid
from types import SimpleNamespace

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"
os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/kaizo_test"

from fastapi.testclient import TestClient
import pytest
import main
import persistence
from phase4_domain_authorization import require_phase4_domain_access
from phase4_route_guard import require_phase4_route_access, require_phase4_tenant_member

persistence.initialize()
client = TestClient(main.app)


@pytest.fixture(autouse=True)
def isolate_outcome_lineage_business_tests_from_tenant_guard():
    # These tests assert override/audit lineage; actual tenant and actor
    # spoofing behavior is verified in dedicated Phase 4 authorization tests.
    test_access = {
        "principal": SimpleNamespace(actor_id="phase4-outcome-test", role="coach"),
        "tenant_id": "phase4-outcome-test-tenant",
        "athlete_id": None,
        "authorization": {"allowed": True, "reason_code": "isolated_business_lineage_test"},
    }
    dependencies = (
        require_phase4_domain_access,
        require_phase4_route_access,
        require_phase4_tenant_member,
    )
    previous = {dependency: main.app.dependency_overrides.get(dependency) for dependency in dependencies}
    for dependency in dependencies:
        main.app.dependency_overrides[dependency] = lambda access=test_access: access
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kaizo_tenants (tenant_id, display_name, status) VALUES (%s, %s, 'ACTIVE') ON CONFLICT (tenant_id) DO UPDATE SET status='ACTIVE'",
                ("phase4-outcome-test-tenant", "Phase 4 Outcome Test"),
            )
            cur.execute(
                "INSERT INTO kaizo_tenant_memberships (tenant_id, subject_id, role, status) VALUES (%s, %s, 'coach', 'ACTIVE') ON CONFLICT (tenant_id, subject_id, role) DO UPDATE SET status='ACTIVE'",
                ("phase4-outcome-test-tenant", "phase4-outcome-test"),
            )
        conn.commit()
    try:
        yield
    finally:
        for dependency, prior_override in previous.items():
            if prior_override is None:
                main.app.dependency_overrides.pop(dependency, None)
            else:
                main.app.dependency_overrides[dependency] = prior_override


def post(path, payload, expected=(200, 201)):
    response = client.post(path, json=payload)
    assert response.status_code in expected, (path, response.status_code, response.text)
    return response.json()


def test_phase4_override_preserves_candidate_and_audit_history():
    suffix = uuid.uuid4().hex[:8]
    coach = "phase4-outcome-test"
    athlete = post("/api/v1/athletes", {"display_name": f"Phase4 Override {suffix}"})
    assessment = post("/api/v1/assessments", {
        "athlete_id": athlete["athlete_id"],
        "template_id": f"P4-OVERRIDE-{suffix}",
        "measurements": {"entry_timing_score": 4},
        "recorded_by": coach,
    })
    problem = post("/api/v1/problem-statements", {
        "athlete_id": athlete["athlete_id"],
        "assessment_id": assessment["assessment_id"],
        "statement": "Timing changes under live resistance",
        "problem_type": "TECHNICAL",
        "created_by": coach,
    })
    evidence = post("/api/v1/evidence", {
        "evidence_id": f"P4-OVERRIDE-EVID-{suffix}",
        "subject_type": "problem",
        "subject_id": problem["problem_id"],
        "evidence_level": "E2",
        "status": "VERIFIED",
        "source_ref": "P4-OVERRIDE-TEST",
        "claim": "Baseline timing score recorded",
        "observed_value": {"entry_timing_score": 4},
        "verified_by": coach,
    })
    diagnosis = post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", {
        "problem_id": problem["problem_id"],
        "evidence_ids": [evidence["evidence_id"]],
        "diagnosis": "Timing under resistance",
        "diagnosed_by": coach,
    })
    candidates = post(f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates", {
        "diagnosis_id": diagnosis["diagnosis_id"],
        "requested_by": coach,
    })["candidates"]
    candidate = candidates[0]

    override = post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review", {
        "candidate_id": candidate["candidate_id"],
        "action": "OVERRIDE",
        "coach_id": coach,
        "override_reason": "Live resistance exposed a constraint not represented by the initial candidate.",
    })
    assert override["status"] == "COACH_OVERRIDDEN"
    assert override["override_reason"]
    assert override["execution_authorized"] is False

    history = client.get(f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review")
    assert history.status_code == 200, history.text
    reviews = history.json()["reviews"]
    assert any(item["review_id"] == override["review_id"] and item["action"] == "OVERRIDE" for item in reviews)

    candidate_readback = client.get(
        f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates"
    )
    assert candidate_readback.status_code == 200, candidate_readback.text
    retained = next(item for item in candidate_readback.json()["candidates"] if item["candidate_id"] == candidate["candidate_id"])
    assert retained == candidate, "the original recommendation must remain intact after coach override"

    decision = post(
        f"/api/v1/decision-candidates/{candidate['candidate_id']}/decision-record",
        {
            "candidate_id": candidate["candidate_id"],
            "coach_id": coach,
            "outcome_intent": "Adapt entry timing work to the observed live-resistance constraint",
        },
    )
    assert decision["coach_action"] == "OVERRIDE"
    assert decision["coach_final_authority"] is True
    assert decision["execution_authorized"] is False

    # Keep business-event assertions separate from the tenant-scoped P14 HTTP ledger.
    actions = [item.get("action") for item in main.AUDIT_LOGS]
    assert "DECISION_CANDIDATE_OVERRIDDEN" in actions
    assert any("DECISION" in (action or "") for action in actions)


def test_phase4_decision_plan_kpi_retest_lineage_keeps_baseline():
    suffix = uuid.uuid4().hex[:8]
    coach = "phase4-outcome-test"
    athlete = post("/api/v1/athletes", {"display_name": f"Phase4 Lineage {suffix}"})
    baseline = post("/api/v1/assessments", {
        "athlete_id": athlete["athlete_id"],
        "template_id": f"P4-LINEAGE-{suffix}",
        "measurements": {"entry_timing_score": 4},
        "recorded_by": coach,
    })
    problem = post("/api/v1/problem-statements", {
        "athlete_id": athlete["athlete_id"],
        "assessment_id": baseline["assessment_id"],
        "statement": "Entry timing needs measurement under resistance",
        "problem_type": "TECHNICAL",
        "created_by": coach,
    })
    evidence = post("/api/v1/evidence", {
        "evidence_id": f"P4-LINEAGE-EVID-{suffix}",
        "subject_type": "assessment",
        "subject_id": baseline["assessment_id"],
        "evidence_level": "E2",
        "status": "VERIFIED",
        "source_ref": "P4-LINEAGE-BASELINE",
        "claim": "Baseline timing score",
        "observed_value": {"entry_timing_score": 4},
        "verified_by": coach,
    })
    diagnosis = post(f"/api/v1/problem-statements/{problem['problem_id']}/diagnosis", {
        "problem_id": problem["problem_id"],
        "evidence_ids": [evidence["evidence_id"]],
        "diagnosis": "Timing decision with measurable baseline",
        "diagnosed_by": coach,
    })
    candidate = post(f"/api/v1/diagnoses/{diagnosis['diagnosis_id']}/decision-candidates", {
        "diagnosis_id": diagnosis["diagnosis_id"],
        "requested_by": coach,
    })["candidates"][0]
    post(f"/api/v1/decision-candidates/{candidate['candidate_id']}/coach-review", {
        "candidate_id": candidate["candidate_id"], "action": "CONFIRM", "coach_id": coach,
    })
    decision = post(
        f"/api/v1/decision-candidates/{candidate['candidate_id']}/decision-record",
        {
            "candidate_id": candidate["candidate_id"],
            "coach_id": coach,
            "outcome_intent": "Improve entry timing while retaining the baseline for comparison",
        },
    )
    plan = post("/api/v1/training-plans", {
        "athlete_id": athlete["athlete_id"],
        "decision_id": decision["decision_id"],
        "title": "Phase 4 draft timing plan",
        "objective": "Improve entry timing under resistance",
        "created_by": coach,
        "constraints": {"duration_min": 60, "state": "PROPOSAL_ONLY"},
    })
    assert plan["status"] == "DRAFT"
    assert plan["execution_authorized"] is False

    kpi_id = f"P4-ENTRY-TIMING-{suffix}"
    definition = post("/api/v1/kpis", {
        "kpi_id": kpi_id,
        "name": "Entry timing score",
        "metric_name": "entry_timing_score",
        "unit": "points",
        "target": 7,
        "direction": "higher_is_better",
        "defined_by": coach,
    })
    baseline_capture = post("/api/v1/kpis/captures", {
        "athlete_id": athlete["athlete_id"],
        "kpi_id": definition["kpi_id"],
        "value": 4,
        "captured_by": coach,
        "assessment_id": baseline["assessment_id"],
    })
    assert baseline_capture["assessment_id"] == baseline["assessment_id"]

    retest = post("/api/v1/features/feat-037/retest-capture", {
        "subject_id": athlete["athlete_id"],
        "actor_id": coach,
        "payload": {
            "athlete_id": athlete["athlete_id"],
            "baseline_ref": baseline["assessment_id"],
            "retest_measurements": {"entry_timing_score": 6},
            "decision_ref": decision["decision_id"],
            "plan_ref": plan["plan_id"],
            "kpi_id": kpi_id,
            "baseline_capture_ref": baseline_capture["capture_id"],
        },
        "evidence_refs": [evidence["evidence_id"], baseline_capture["capture_id"]],
        "coach_final_authority": True,
        "execution_authorized": False,
    })
    assert retest["feature_id"] == "FEAT-037"
    assert retest["payload"]["baseline_ref"] == baseline["assessment_id"]
    assert retest["payload"]["decision_ref"] == decision["decision_id"]
    assert retest["payload"]["plan_ref"] == plan["plan_id"]

    comparison = post("/api/v1/features/feat-038/before-after-comparison", {
        "subject_id": athlete["athlete_id"],
        "actor_id": coach,
        "payload": {
            "before_ref": baseline["assessment_id"],
            "after_ref": retest["record_id"],
            "comparison": {
                "kpi_id": kpi_id,
                "baseline_value": 4,
                "retest_value": 6,
                "interpretation": "Observed numeric change; no causal claim inferred by this test",
            },
            "decision_ref": decision["decision_id"],
            "plan_ref": plan["plan_id"],
            "baseline_capture_ref": baseline_capture["capture_id"],
        },
        "evidence_refs": [evidence["evidence_id"], baseline_capture["capture_id"], retest["record_id"]],
        "coach_final_authority": True,
        "execution_authorized": False,
    })
    assert comparison["feature_id"] == "FEAT-038"
    assert comparison["payload"]["before_ref"] == baseline["assessment_id"]
    assert comparison["payload"]["after_ref"] == retest["record_id"]
    assert comparison["payload"]["comparison"]["baseline_value"] == 4
    assert comparison["payload"]["comparison"]["retest_value"] == 6
    assert comparison["execution_authorized"] is False

    baseline_readback = client.get(f"/api/v1/assessments/{baseline['assessment_id']}")
    assert baseline_readback.status_code == 200, baseline_readback.text
    assert baseline_readback.json()["measurements"]["entry_timing_score"] == 4


if __name__ == "__main__":
    test_phase4_override_preserves_candidate_and_audit_history()
    test_phase4_decision_plan_kpi_retest_lineage_keeps_baseline()
    print("Phase 4 override and outcome lineage acceptance passed")
