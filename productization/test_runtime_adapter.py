import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from productization.runtime_adapter import (
    CoreRuntimeGateway,
    ProductCoreRuntimeAdapter,
    RuntimeAuthorizationError,
    RuntimeContext,
)


DECISION_PAYLOAD = {
    "case_id": "CASE-P7-E2E",
    "athlete_id": "athlete-1",
    "decision": {"type": "SELECTION", "value": "candidate-a"},
    "intervention": {"type": "DRILL", "value": "seoi"},
    "response_kpi": {"kpi": "entry_quality", "value": 7},
    "retest": {"result": "PASS"},
}


def setup_function():
    from productization import coach_roster
    coach_roster.reset_memory_state()
    athlete = coach_roster.create_owned_athlete(
        tenant_id="academy-a", coach_actor_id="coach-1",
        display_name="Runtime adapter ownership test",
    )
    DECISION_PAYLOAD["athlete_id"] = athlete["athlete_id"]


def test_adapter_binds_to_real_frozen_core():
    adapter = ProductCoreRuntimeAdapter(CoreRuntimeGateway())
    result = adapter.request_decision(
        RuntimeContext("coach-1", "coach", "academy-a", "athlete-1"),
        "academy-a",
        DECISION_PAYLOAD,
    )
    assert result["status"] == "LOOP_COMPLETED"
    assert result["coach_final_authority"] is True


def test_real_core_cannot_be_called_with_execution_authorized_true():
    gateway = CoreRuntimeGateway()
    with pytest.raises(RuntimeAuthorizationError):
        gateway.request_decision(
            actor_id="coach-1",
            tenant_id="academy-a",
            role="coach",
            payload=DECISION_PAYLOAD,
            execution_authorized=True,
        )


def test_four_role_runtime_boundaries_and_tenant_isolation():
    adapter = ProductCoreRuntimeAdapter(CoreRuntimeGateway())
    academy = RuntimeContext("academy-1", "academy", "academy-a")
    coach = RuntimeContext("coach-1", "coach", "academy-a", "athlete-1", coach_approved=True)
    athlete = RuntimeContext("athlete-1", "athlete", "academy-a", "athlete-1")
    parent = RuntimeContext("parent-1", "parent", "academy-a", "athlete-1")

    # Academy and Coach can request approved exports; Athlete and Parent cannot.
    assert adapter.export_approved(academy, "academy-a", ["REC-001"])["execution_authorized"] is False
    assert adapter.export_approved(coach, "academy-a", ["REC-002"])["execution_authorized"] is False
    with pytest.raises(RuntimeAuthorizationError):
        adapter.export_approved(athlete, "academy-a", ["REC-003"])
    with pytest.raises(RuntimeAuthorizationError):
        adapter.export_approved(parent, "academy-a", ["REC-004"])

    # Only Coach can request/record a governed Core decision.
    assert adapter.request_decision(coach, "academy-a", DECISION_PAYLOAD)["coach_final_authority"] is True
    with pytest.raises(RuntimeAuthorizationError):
        adapter.request_decision(academy, "academy-a", DECISION_PAYLOAD)
    with pytest.raises(RuntimeAuthorizationError):
        adapter.request_decision(athlete, "academy-a", DECISION_PAYLOAD)
    with pytest.raises(RuntimeAuthorizationError):
        adapter.request_decision(parent, "academy-a", DECISION_PAYLOAD)

    # Athlete/Parent cannot mutate; coach approval is mandatory.
    assert adapter.record_intervention(coach, "academy-a", DECISION_PAYLOAD)["status"] == "LOOP_COMPLETED"
    for ctx in (academy, athlete, parent):
        with pytest.raises(RuntimeAuthorizationError):
            adapter.record_intervention(ctx, "academy-a", DECISION_PAYLOAD)

    # Cross-tenant access is denied for every commercial role.
    for ctx in (academy, coach, athlete, parent):
        with pytest.raises(RuntimeAuthorizationError, match="cross-tenant"):
            adapter.export_approved(ctx, "academy-b", ["REC-X"])


def test_coach_approval_is_required_before_intervention():
    adapter = ProductCoreRuntimeAdapter(CoreRuntimeGateway())
    with pytest.raises(RuntimeAuthorizationError, match="Coach approval"):
        adapter.record_intervention(
            RuntimeContext("coach-1", "coach", "academy-a", "athlete-1", coach_approved=False),
            "academy-a",
            DECISION_PAYLOAD,
        )



def test_adapter_rejects_an_athlete_not_owned_by_the_verified_coach():
    adapter = ProductCoreRuntimeAdapter(CoreRuntimeGateway())
    payload = {**DECISION_PAYLOAD, "athlete_id": "not-owned-by-coach-1"}
    with pytest.raises(RuntimeAuthorizationError, match="athlete not found"):
        adapter.request_decision(
            RuntimeContext("coach-1", "coach", "academy-a"),
            "academy-a",
            payload,
        )



def test_adapter_supports_adaptation_only_for_an_owned_decision():
    import main
    adapter = ProductCoreRuntimeAdapter(CoreRuntimeGateway())
    athlete_id = DECISION_PAYLOAD["athlete_id"]
    main.DECISION_RECORDS["decision-adapter-1"] = {
        "decision_id": "decision-adapter-1", "athlete_id": athlete_id
    }
    payload = {
        "athlete_id": athlete_id,
        "decision_id": "decision-adapter-1",
        "case_id": "CASE-ADAPT-1",
        "operation": "individual_adaptation",
        "common_core": {"principle": "retain"},
        "dynamic_inputs": {"readiness": "medium"},
        "individual_change": {"load": "adjust"},
    }
    coach = RuntimeContext("coach-1", "coach", "academy-a")
    result = adapter.adapt_decision(coach, "academy-a", payload)
    assert result["status"] == "ADAPTED"
    assert result["decision_id"] == "decision-adapter-1"
    assert result["recorded_by"] == "coach-1"
    assert result.get("execution_authorized", False) is False

    payload["decision_id"] = "decision-not-owned"
    with pytest.raises(RuntimeAuthorizationError, match="decision not found"):
        adapter.adapt_decision(coach, "academy-a", payload)
