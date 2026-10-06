import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from productization.runtime_adapter import CoreRuntimeGateway, ProductCoreRuntimeAdapter, RuntimeContext


def test_adapter_binds_to_real_frozen_core():
    adapter = ProductCoreRuntimeAdapter(CoreRuntimeGateway())
    result = adapter.request_decision(
        RuntimeContext("coach-1", "coach", "academy-a", "athlete-1"),
        "academy-a",
        {
            "case_id": "CASE-P7-001",
            "decision": {"type": "SELECTION", "value": "candidate-a"},
            "intervention": {"type": "DRILL", "value": "seoi"},
            "response_kpi": {"kpi": "entry_quality", "value": 7},
            "retest": {"result": "PASS"},
        },
    )
    assert result["status"] == "LOOP_COMPLETED"
    assert result["coach_final_authority"] is True


def test_real_core_cannot_be_called_with_execution_authorized_true():
    gateway = CoreRuntimeGateway()
    with pytest.raises(Exception):
        gateway.request_decision(
            actor_id="coach-1",
            tenant_id="academy-a",
            role="coach",
            payload={
                "case_id": "CASE-P7-NEG",
                "decision": {"x": 1},
                "intervention": {"x": 1},
                "response_kpi": {"x": 1},
                "retest": {"x": 1},
            },
            execution_authorized=True,
        )


def test_adapter_still_blocks_cross_tenant_before_core():
    adapter = ProductCoreRuntimeAdapter(CoreRuntimeGateway())
    with pytest.raises(Exception, match="cross-tenant"):
        adapter.request_decision(
            RuntimeContext("coach-1", "coach", "academy-a"),
            "academy-b",
            {},
        )
