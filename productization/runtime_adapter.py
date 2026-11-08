"""Phase 7 product-to-Core runtime adapter.

This adapter binds commercial product operations to the frozen Core runtime
functions without granting execution authority.
"""
from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeContext:
    actor_id: str
    role: str
    tenant_id: str
    resource_owner_id: str | None = None
    coach_approved: bool = False


class RuntimeAuthorizationError(PermissionError):
    pass


class CoreRuntimeGateway:
    """Private bridge to Core decision executors; public legacy routes are retired."""

    def __init__(self):
        from main import _execute_decision_loop, _execute_adaptation
        self._decision_loop = _execute_decision_loop
        self._adaptation = _execute_adaptation

    @staticmethod
    def _require_scoped_payload(payload: Mapping[str, Any]) -> None:
        if not str(payload.get("athlete_id") or "").strip():
            raise RuntimeAuthorizationError("athlete_id is required for a scoped Coach decision")

    def request_decision(self, *, actor_id: str, tenant_id: str, role: str,
                         payload: Mapping[str, Any], execution_authorized: bool) -> Any:
        if execution_authorized:
            raise RuntimeAuthorizationError("execution authorization is forbidden")
        self._require_scoped_payload(payload)
        from main import DecisionLoopRequest
        return self._decision_loop(DecisionLoopRequest(
            case_id=str(payload["case_id"]),
            athlete_id=str(payload["athlete_id"]),
            decision=dict(payload["decision"]),
            intervention=dict(payload["intervention"]),
            response_kpi=dict(payload["response_kpi"]),
            retest=dict(payload["retest"]),
            coach_final_authority=True,
        ))

    def adapt_decision(self, *, actor_id: str, tenant_id: str, role: str,
                       payload: Mapping[str, Any], execution_authorized: bool) -> Any:
        if execution_authorized:
            raise RuntimeAuthorizationError("execution authorization is forbidden")
        self._require_scoped_payload(payload)
        from main import AdaptationRequest
        return self._adaptation(AdaptationRequest(
            case_id=str(payload["case_id"]),
            athlete_id=str(payload["athlete_id"]),
            decision_id=str(payload["decision_id"]),
            operation=str(payload["operation"]),
            common_core=dict(payload["common_core"]),
            dynamic_inputs=dict(payload["dynamic_inputs"]),
            individual_change=payload.get("individual_change"),
            team_change=payload.get("team_change"),
            composition_change=payload.get("composition_change"),
            coach_final_authority=True,
        ))

    def record_intervention(self, *, actor_id: str, tenant_id: str, role: str,
                            payload: Mapping[str, Any], execution_authorized: bool) -> Any:
        if execution_authorized:
            raise RuntimeAuthorizationError("execution authorization is forbidden")
        return self.request_decision(
            actor_id=actor_id, tenant_id=tenant_id, role=role,
            payload=payload, execution_authorized=False
        )

    def export_approved(self, *, actor_id: str, tenant_id: str, role: str,
                        approved_record_ids: list[str], execution_authorized: bool) -> Any:
        if execution_authorized:
            raise RuntimeAuthorizationError("execution authorization is forbidden")
        return {
            "status": "APPROVAL_REQUIRED",
            "approved_record_ids": list(approved_record_ids),
            "execution_authorized": False,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "role": role,
        }


class ProductCoreRuntimeAdapter:
    ROLE_SET = {"academy", "coach", "athlete", "parent"}

    def __init__(self, core: Any | None = None):
        self.core = core or CoreRuntimeGateway()

    def _authorize(self, ctx: RuntimeContext, resource_tenant_id: str) -> None:
        if not ctx.actor_id or not ctx.tenant_id:
            raise RuntimeAuthorizationError("authenticated identity and tenant are required")
        if ctx.tenant_id != resource_tenant_id:
            raise RuntimeAuthorizationError("cross-tenant access denied")
        if ctx.role not in self.ROLE_SET:
            raise RuntimeAuthorizationError("unsupported product role")

    def request_decision(self, ctx: RuntimeContext, resource_tenant_id: str,
                         payload: Mapping[str, Any]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role != "coach":
            raise RuntimeAuthorizationError("only Coach may request a Core decision")
        return self.core.request_decision(
            actor_id=ctx.actor_id, tenant_id=ctx.tenant_id, role=ctx.role,
            payload=dict(payload), execution_authorized=False
        )

    def adapt_decision(self, ctx: RuntimeContext, resource_tenant_id: str,
                       payload: Mapping[str, Any]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role != "coach":
            raise RuntimeAuthorizationError("only Coach may adapt a decision")
        return self.core.adapt_decision(
            actor_id=ctx.actor_id, tenant_id=ctx.tenant_id, role=ctx.role,
            payload=dict(payload), execution_authorized=False
        )

    def record_intervention(self, ctx: RuntimeContext, resource_tenant_id: str,
                            payload: Mapping[str, Any]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role != "coach":
            raise RuntimeAuthorizationError("only Coach may record intervention")
        if not ctx.coach_approved:
            raise RuntimeAuthorizationError("Coach approval is required")
        return self.core.record_intervention(
            actor_id=ctx.actor_id, tenant_id=ctx.tenant_id, role=ctx.role,
            payload=dict(payload), execution_authorized=False
        )

    def export_approved(self, ctx: RuntimeContext, resource_tenant_id: str,
                        record_ids: list[str]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role not in {"academy", "coach"}:
            raise RuntimeAuthorizationError("role cannot export records")
        return self.core.export_approved(
            actor_id=ctx.actor_id, tenant_id=ctx.tenant_id, role=ctx.role,
            approved_record_ids=list(record_ids), execution_authorized=False
        )
