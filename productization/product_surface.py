"""Commercial KAIZO product runtime surface.

This is a server-side surface contract implementation over ProductCoreRuntimeAdapter.
It exposes governed role views and operations without execution authority.
"""
from dataclasses import dataclass
from typing import Any, Mapping

from .runtime_adapter import ProductCoreRuntimeAdapter, RuntimeAuthorizationError, RuntimeContext


@dataclass(frozen=True)
class ProductSurface:
    runtime: ProductCoreRuntimeAdapter

    def navigation(self, ctx: RuntimeContext) -> dict[str, Any]:
        if ctx.role == "academy":
            surfaces = ["dashboard", "groups", "coaches", "athletes", "approved_reports"]
        elif ctx.role == "coach":
            surfaces = ["decision_cases", "adaptation", "decision_loop", "digital_twin", "audit"]
        elif ctx.role == "athlete":
            surfaces = ["my_progress", "approved_feedback", "competition_results"]
        elif ctx.role == "parent":
            surfaces = ["linked_athlete", "progress", "approved_reports"]
        else:
            raise RuntimeAuthorizationError("unsupported product role")
        return {
            "role": ctx.role,
            "tenant_id": ctx.tenant_id,
            "surfaces": surfaces,
            "execution_authorized": False,
            "coach_final_authority": True,
        }

    def request_decision(self, ctx: RuntimeContext, resource_tenant_id: str,
                         payload: Mapping[str, Any]) -> Any:
        result = self.runtime.request_decision(ctx=ctx, resource_tenant_id=resource_tenant_id, payload=payload)
        if isinstance(result, dict):
            result = {**result, "execution_authorized": False}
        return result

    def record_intervention(self, ctx: RuntimeContext, resource_tenant_id: str,
                            payload: Mapping[str, Any]) -> Any:
        result = self.runtime.record_intervention(ctx=ctx, resource_tenant_id=resource_tenant_id, payload=payload)
        if isinstance(result, dict):
            result = {**result, "execution_authorized": False}
        return result

    def approved_export(self, ctx: RuntimeContext, resource_tenant_id: str,
                        record_ids: list[str]) -> Any:
        return self.runtime.export_approved(ctx=ctx, resource_tenant_id=resource_tenant_id, record_ids=record_ids)

    def athlete_progress(self, ctx: RuntimeContext, resource_tenant_id: str,
                         athlete_id: str, records: list[Mapping[str, Any]]) -> dict[str, Any]:
        self._read_scope(ctx, resource_tenant_id, athlete_id)
        if ctx.role not in {"athlete", "coach", "academy"}:
            raise RuntimeAuthorizationError("role cannot view athlete progress")
        return {"athlete_id": athlete_id, "records": list(records), "approved_only": True,
                "execution_authorized": False}

    def parent_progress(self, ctx: RuntimeContext, resource_tenant_id: str,
                        linked_athlete_id: str, records: list[Mapping[str, Any]]) -> dict[str, Any]:
        self._read_scope(ctx, resource_tenant_id, linked_athlete_id)
        if ctx.role != "parent":
            raise RuntimeAuthorizationError("only Parent may use linked-athlete view")
        if ctx.resource_owner_id != linked_athlete_id:
            raise RuntimeAuthorizationError("explicit athlete linkage is required")
        return {"athlete_id": linked_athlete_id, "records": list(records), "approved_only": True,
                "execution_authorized": False}

    @staticmethod
    def _read_scope(ctx: RuntimeContext, resource_tenant_id: str, owner_id: str) -> None:
        if not ctx.actor_id or not ctx.tenant_id:
            raise RuntimeAuthorizationError("authenticated identity and tenant are required")
        if ctx.tenant_id != resource_tenant_id:
            raise RuntimeAuthorizationError("cross-tenant access denied")
        if not owner_id:
            raise RuntimeAuthorizationError("resource owner is required")
