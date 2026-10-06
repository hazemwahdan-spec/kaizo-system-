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
    """Concrete gateway to the frozen backend/main.py Core functions."""

    def __init__(self):
        from main import decision_loop, adapt_decision
        self._decision_loop = decision_loop
        self._adapt_decision = adapt_decision

    def request_decision(self, *, actor_id: str, tenant_id: str, role: str,
                         payload: Mapping[str, Any], execution_authorized: bool) -> Any:
        if execution_authorized:
            raise RuntimeAuthorizationError("execution authorization is forbidden")
        from main import DecisionLoopRequest
        return self._decision_loop(DecisionLoopRequest(
            case_id=str(payload["case_id"]),
            decision=dict(payload["decision"]),
            intervention=dict(payload["intervention"]),
            response_kpi=dict(payload["response_kpi"]),
            retest=dict(payload["retest"]),
            coach_final_authority=True,
        ))

    def record_intervention(self, *, actor_id: str, tenant_id: str, role: str,
                            payload: Mapping[str, Any], execution_authorized: bool) -> Any:
        if execution_authorized:
            raise RuntimeAuthorizationError("execution authorization is forbidden")
        # Core's Decision Loop records the intervention as part of the governed cycle.
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
    def __init__(self, core: Any | None = None):
        self.core = core or CoreRuntimeGateway()

    def _authorize(self, ctx: RuntimeContext, resource_tenant_id: str) -> None:
        if not ctx.actor_id or not ctx.tenant_id:
            raise RuntimeAuthorizationError("authenticated identity and tenant are required")
        if ctx.tenant_id != resource_tenant_id:
            raise RuntimeAuthorizationError("cross-tenant access denied")
        if ctx.role not in {"academy", "coach", "athlete", "parent"}:
            raise RuntimeAuthorizationError("unsupported product role")

    def request_decision(self, ctx: RuntimeContext, resource_tenant_id: str,
                         payload: Mapping[str, Any]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        return self.core.request_decision(
            actor_id=ctx.actor_id, tenant_id=ctx.tenant_id, role=ctx.role,
            payload=dict(payload), execution_authorized=False
        )

    def record_intervention(self, ctx: RuntimeContext, resource_tenant_id: str,
                            payload: Mapping[str, Any]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role not in {"academy", "coach"}:
            raise RuntimeAuthorizationError("role cannot record intervention")
        if ctx.role == "coach" and not ctx.coach_approved:
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
