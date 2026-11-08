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


def _require_owned_coach_athlete(actor_id: str, tenant_id: str, role: str,
                                 payload: Mapping[str, Any]) -> str:
    if role != "coach":
        raise RuntimeAuthorizationError("only Coach may enter the Core decision loop")
    athlete_id = str(payload.get("athlete_id") or "").strip()
    if not athlete_id:
        raise RuntimeAuthorizationError("athlete_id is required for Coach decision access")
    from productization import coach_roster
    athlete = coach_roster.get_owned_athlete(
        tenant_id=tenant_id, coach_actor_id=actor_id, athlete_id=athlete_id
    )
    if athlete is None:
        raise RuntimeAuthorizationError("athlete not found in Coach scope")
    return athlete_id


class CoreRuntimeGateway:
    """Concrete gateway to the frozen backend/main.py Core functions."""

    def __init__(self):
        from main import _execute_decision_loop
        self._decision_loop = _execute_decision_loop

    def request_decision(self, *, actor_id: str, tenant_id: str, role: str,
                         payload: Mapping[str, Any], execution_authorized: bool) -> Any:
        if execution_authorized:
            raise RuntimeAuthorizationError("execution authorization is forbidden")
        _require_owned_coach_athlete(actor_id, tenant_id, role, payload)
        from main import DecisionLoopRequest
        return self._decision_loop(DecisionLoopRequest(
            case_id=str(payload["case_id"]),
            athlete_id=str(payload["athlete_id"]),
            decision=dict(payload["decision"]),
            intervention=dict(payload["intervention"]),
            response_kpi=dict(payload["response_kpi"]),
            retest=dict(payload["retest"]),
            coach_final_authority=True,
        ), actor_id=actor_id)

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

    @staticmethod
    def _authorize_owned_athlete(ctx: RuntimeContext, payload: Mapping[str, Any]) -> None:
        _require_owned_coach_athlete(ctx.actor_id, ctx.tenant_id, ctx.role, payload)

    def request_decision(self, ctx: RuntimeContext, resource_tenant_id: str,
                         payload: Mapping[str, Any]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role != "coach":
            raise RuntimeAuthorizationError("only Coach may request a Core decision")
        self._authorize_owned_athlete(ctx, payload)
        return self.core.request_decision(
            actor_id=ctx.actor_id, tenant_id=ctx.tenant_id, role=ctx.role,
            payload=dict(payload), execution_authorized=False
        )

    def record_intervention(self, ctx: RuntimeContext, resource_tenant_id: str,
                            payload: Mapping[str, Any]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role != "coach":
            raise RuntimeAuthorizationError("only Coach may record intervention")
        self._authorize_owned_athlete(ctx, payload)
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
