"""Commercial product API surface for KAIZO Phase 7."""
from typing import Any, Dict, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .product_surface import ProductSurface
from .runtime_adapter import ProductCoreRuntimeAdapter, RuntimeAuthorizationError, RuntimeContext

router = APIRouter(prefix="/api/v1/product", tags=["Commercial Product"])
surface = ProductSurface(ProductCoreRuntimeAdapter())


def ctx(actor_id: str, role: str, tenant_id: str, owner: str | None) -> RuntimeContext:
    return RuntimeContext(actor_id=actor_id, role=role, tenant_id=tenant_id, resource_owner_id=owner)


def deny(exc: Exception):
    raise HTTPException(status_code=403, detail=str(exc))


@router.get("/navigation")
def navigation(
    actor_id: str = Header(..., alias="X-KAIZO-Actor"),
    role: str = Header(..., alias="X-KAIZO-Role"),
    tenant_id: str = Header(..., alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    try:
        return surface.navigation(ctx(actor_id, role, tenant_id, owner))
    except RuntimeAuthorizationError as exc:
        deny(exc)


class DecisionRequest(BaseModel):
    resource_tenant_id: str
    case_id: str
    decision: Dict[str, Any]
    intervention: Dict[str, Any]
    response_kpi: Dict[str, Any]
    retest: Dict[str, Any]


@router.post("/decision")
def decision(
    req: DecisionRequest,
    actor_id: str = Header(..., alias="X-KAIZO-Actor"),
    role: str = Header(..., alias="X-KAIZO-Role"),
    tenant_id: str = Header(..., alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    try:
        return surface.request_decision(ctx(actor_id, role, tenant_id, owner), req.resource_tenant_id,
                                        req.model_dump(exclude={"resource_tenant_id"}))
    except RuntimeAuthorizationError as exc:
        deny(exc)


class InterventionRequest(DecisionRequest):
    coach_approved: bool = False


@router.post("/intervention")
def intervention(
    req: InterventionRequest,
    actor_id: str = Header(..., alias="X-KAIZO-Actor"),
    role: str = Header(..., alias="X-KAIZO-Role"),
    tenant_id: str = Header(..., alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    try:
        c = ctx(actor_id, role, tenant_id, owner)
        c = RuntimeContext(c.actor_id, c.role, c.tenant_id, c.resource_owner_id, req.coach_approved)
        return surface.record_intervention(c, req.resource_tenant_id, req.model_dump(exclude={"resource_tenant_id", "coach_approved"}))
    except RuntimeAuthorizationError as exc:
        deny(exc)


@router.get("/athletes/{athlete_id}/progress")
def progress(
    athlete_id: str,
    resource_tenant_id: str,
    actor_id: str = Header(..., alias="X-KAIZO-Actor"),
    role: str = Header(..., alias="X-KAIZO-Role"),
    tenant_id: str = Header(..., alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    if role == "athlete" and owner != athlete_id:
        raise HTTPException(status_code=403, detail="athlete self-scope required")
    try:
        return surface.athlete_progress(ctx(actor_id, role, tenant_id, owner), resource_tenant_id, athlete_id, [])
    except RuntimeAuthorizationError as exc:
        deny(exc)


@router.get("/parents/linked/{athlete_id}/progress")
def parent_progress(
    athlete_id: str,
    resource_tenant_id: str,
    actor_id: str = Header(..., alias="X-KAIZO-Actor"),
    role: str = Header(..., alias="X-KAIZO-Role"),
    tenant_id: str = Header(..., alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    try:
        return surface.parent_progress(ctx(actor_id, role, tenant_id, owner), resource_tenant_id, athlete_id, [])
    except RuntimeAuthorizationError as exc:
        deny(exc)
