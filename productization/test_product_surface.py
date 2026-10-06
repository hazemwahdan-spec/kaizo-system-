from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from productization.product_surface import ProductSurface
from productization.runtime_adapter import RuntimeAuthorizationError, RuntimeContext


class StubRuntime:
    def request_decision(self, **kwargs):
        assert kwargs["execution_authorized"] is False
        return {"status": "LOOP_COMPLETED", "coach_final_authority": True}

    def record_intervention(self, **kwargs):
        assert kwargs["execution_authorized"] is False
        return {"status": "LOOP_COMPLETED"}

    def export_approved(self, **kwargs):
        assert kwargs["execution_authorized"] is False
        return {"status": "APPROVAL_REQUIRED", "execution_authorized": False}


def surface():
    return ProductSurface(StubRuntime())


def test_all_roles_receive_only_governed_navigation():
    for role in ("academy", "coach", "athlete", "parent"):
        result = surface().navigation(RuntimeContext("actor", role, "tenant"))
        assert result["execution_authorized"] is False
        assert result["coach_final_authority"] is True
        assert result["surfaces"]


def test_only_coach_can_request_decision():
    payload = {
        "case_id": "CASE-1",
        "decision": {"choice": "adapt"},
        "intervention": {"drill": "seoi"},
        "response_kpi": {"score": 1},
        "retest": {"score": 1},
    }
    result = surface().request_decision(
        RuntimeContext("coach-1", "coach", "tenant", "athlete-1"),
        "tenant", payload
    )
    assert result["status"] == "LOOP_COMPLETED"
    assert result["coach_final_authority"] is True

    for role in ("academy", "athlete", "parent"):
        try:
            surface().request_decision(RuntimeContext("actor", role, "tenant"), "tenant", payload)
            assert False
        except RuntimeAuthorizationError:
            pass


def test_parent_requires_explicit_linkage():
    ctx = RuntimeContext("parent-1", "parent", "tenant", "athlete-1")
    assert surface().parent_progress(ctx, "tenant", "athlete-1", [{"id": "R1"}])["approved_only"]
    try:
        surface().parent_progress(
            RuntimeContext("parent-1", "parent", "tenant", "athlete-2"),
            "tenant", "athlete-1", []
        )
        assert False
    except RuntimeAuthorizationError:
        pass


def test_cross_tenant_access_is_denied():
    ctx = RuntimeContext("coach-1", "coach", "tenant-a")
    try:
        surface().navigation(ctx)
        surface().request_decision(ctx, "tenant-b", {})
        assert False
    except RuntimeAuthorizationError:
        pass


def test_exports_remain_approval_gated_and_non_executing():
    result = surface().approved_export(
        RuntimeContext("coach-1", "coach", "tenant"),
        "tenant", ["APPROVED-1"]
    )
    assert result["execution_authorized"] is False
