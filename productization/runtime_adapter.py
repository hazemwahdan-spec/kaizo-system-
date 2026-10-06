"""Phase 7 product-to-Core runtime adapter.

Governance boundary: this adapter can request/record Core operations but never
authorizes execution. Authentication, tenant scope, and Coach Final Authority
are explicit inputs to every mutation.
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


class ProductCoreRuntimeAdapter:
    """Minimal deterministic boundary for commercial product integration."""

    MUTATING_ROLES = {"academy", "coach"}

    def __init__(self, core: Any):
        self.core = core

    def _authorize(self, ctx: RuntimeContext, resource_tenant_id: str) -> None:
        if not ctx.actor_id or not ctx.tenant_id:
            raise RuntimeAuthorizationError("authenticated identity and tenant are required")
        if ctx.tenant_id != resource_tenant_id:
            raise RuntimeAuthorizationError("cross-tenant access denied")
        if ctx.role not in {"academy", "coach", "athlete", "parent"}:
            raise RuntimeAuthorizationError("unsupported product role")

    def request_decision(
        self, ctx: RuntimeContext, resource_tenant_id: str, payload: Mapping[str, Any]
    ) -> Any:
        self._authorize(ctx, resource_tenant_id)
        return self.core.request_decision(
            actor_id=ctx.actor_id,
            tenant_id=ctx.tenant_id,
            role=ctx.role,
            payload=dict(payload),
            execution_authorized=False,
        )

    def record_intervention(
        self, ctx: RuntimeContext, resource_tenant_id: str, payload: Mapping[str, Any]
    ) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role not in self.MUTATING_ROLES:
            raise RuntimeAuthorizationError("role cannot record intervention")
        if ctx.role == "coach" and not ctx.coach_approved:
            raise RuntimeAuthorizationError("Coach approval is required")
        return self.core.record_intervention(
            actor_id=ctx.actor_id,
            tenant_id=ctx.tenant_id,
            role=ctx.role,
            payload=dict(payload),
            execution_authorized=False,
        )

    def export_approved(self, ctx: RuntimeContext, resource_tenant_id: str, record_ids: list[str]) -> Any:
        self._authorize(ctx, resource_tenant_id)
        if ctx.role not in self.MUTATING_ROLES:
            raise RuntimeAuthorizationError("role cannot export records")
        return self.core.export_approved(
            actor_id=ctx.actor_id,
            tenant_id=ctx.tenant_id,
            role=ctx.role,
            approved_record_ids=list(record_ids),
            execution_authorized=False,
        )
