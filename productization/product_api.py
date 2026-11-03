"""Commercial product API surface for KAIZO Phase 7."""
from typing import Any, Dict, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .product_surface import ProductSurface
from .runtime_adapter import ProductCoreRuntimeAdapter, RuntimeAuthorizationError, RuntimeContext
from .identity import IdentityNotConfiguredError, resolve_principal, resolve_bearer_principal, verify_bearer_token
from . import coach_roster, coach_groups

router = APIRouter(prefix="/api/v1/product", tags=["Commercial Product"])


@router.get("/auth/oidc/verify")
def verify_oidc(
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Live OIDC verification endpoint for standard JWT validation."""
    try:
        return verify_bearer_token(authorization)
    except IdentityNotConfiguredError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

_surface: ProductSurface | None = None

def get_surface() -> ProductSurface:
    global _surface
    if _surface is None:
        _surface = ProductSurface(ProductCoreRuntimeAdapter())
    return _surface


def ctx(actor_id: str, role: str, tenant_id: str, owner: str | None, authorization: str | None = None) -> RuntimeContext:
    try:
        principal = resolve_principal(actor_id, role, tenant_id, owner, authorization)
    except IdentityNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return RuntimeContext(
        actor_id=principal.actor_id,
        role=principal.role,
        tenant_id=principal.tenant_id,
        resource_owner_id=principal.resource_owner_id,
    )


def deny(exc: Exception):
    raise HTTPException(status_code=403, detail=str(exc))


@router.get("/navigation")
def navigation(
    actor_id: str = Header(..., alias="X-KAIZO-Actor"),
    role: str = Header(..., alias="X-KAIZO-Role"),
    tenant_id: str = Header(..., alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    try:
        return get_surface().navigation(ctx(actor_id, role, tenant_id, owner, authorization))
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
    authorization: str | None = Header(None, alias="Authorization"),
):
    try:
        return get_surface().request_decision(ctx(actor_id, role, tenant_id, owner, authorization), req.resource_tenant_id,
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
    authorization: str | None = Header(None, alias="Authorization"),
):
    try:
        c = ctx(actor_id, role, tenant_id, owner, authorization)
        c = RuntimeContext(c.actor_id, c.role, c.tenant_id, c.resource_owner_id, req.coach_approved)
        return get_surface().record_intervention(c, req.resource_tenant_id, req.model_dump(exclude={"resource_tenant_id", "coach_approved"}))
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
    authorization: str | None = Header(None, alias="Authorization"),
):
    if role == "athlete" and owner != athlete_id:
        raise HTTPException(status_code=403, detail="athlete self-scope required")
    try:
        return get_surface().athlete_progress(ctx(actor_id, role, tenant_id, owner, authorization), resource_tenant_id, athlete_id, [])
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
    authorization: str | None = Header(None, alias="Authorization"),
):
    try:
        return get_surface().parent_progress(ctx(actor_id, role, tenant_id, owner, authorization), resource_tenant_id, athlete_id, [])
    except RuntimeAuthorizationError as exc:
        deny(exc)


# Coach roster ownership boundary. Identity scope is derived server-side.
class CoachAthleteCreateRequest(BaseModel):
    display_name: str
    metadata: Dict[str, Any] = {}


def verified_coach_scope(
    authorization: str | None,
    actor_id: str | None,
    role: str | None,
    tenant_id: str | None,
    owner: str | None = None,
):
    import os
    mode = os.getenv("KAIZO_IDENTITY_MODE", "production").strip().lower()
    try:
        if mode in {"oidc", "oauth2", "external"}:
            principal = resolve_bearer_principal(authorization)
        elif mode == "development":
            principal = resolve_principal(actor_id or "", role or "", tenant_id or "",
                                          owner, authorization)
        else:
            raise IdentityNotConfiguredError("production identity is fail-closed")
    except IdentityNotConfiguredError as exc:
        raise HTTPException(status_code=401, detail="verified authentication required") from exc
    if principal.role != "coach":
        raise HTTPException(status_code=403, detail="Coach role required")
    if not principal.actor_id or not principal.tenant_id:
        raise HTTPException(status_code=403, detail="Coach tenant scope required")
    return principal


def _coach_scope(authorization, actor_id, role, tenant_id, owner):
    return verified_coach_scope(authorization, actor_id, role, tenant_id, owner)


@router.post("/coach/athletes", status_code=201)
def create_coach_athlete(
    req: CoachAthleteCreateRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    try:
        athlete = coach_roster.create_owned_athlete(
            tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
            display_name=req.display_name, metadata=req.metadata)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**athlete, "coach_final_authority": True, "execution_authorized": False}


@router.get("/coach/athletes")
def list_coach_athletes(
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    athletes = coach_roster.list_owned_athletes(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id)
    return {"total": len(athletes), "athletes": athletes,
            "coach_final_authority": True, "execution_authorized": False}


@router.get("/coach/athletes/{athlete_id}")
def get_coach_athlete(
    athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    athlete = coach_roster.get_owned_athlete(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id)
    if athlete is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return {**athlete, "coach_final_authority": True, "execution_authorized": False}




# FEAT-003: training groups remain inside the verified Coach + tenant boundary.
class CoachGroupCreateRequest(BaseModel):
    name: str

class CoachGroupAthleteRequest(BaseModel):
    athlete_id: str

@router.post("/coach/groups", status_code=201)
def create_coach_group(
    req: CoachGroupCreateRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    try:
        group = coach_groups.create_group(tenant_id=principal.tenant_id,
                                          coach_actor_id=principal.actor_id,
                                          name=req.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**group, "coach_final_authority": True, "execution_authorized": False}

@router.get("/coach/groups")
def list_coach_groups(
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    groups = coach_groups.list_groups(tenant_id=principal.tenant_id,
                                      coach_actor_id=principal.actor_id)
    return {"total": len(groups), "groups": groups,
            "coach_final_authority": True, "execution_authorized": False}

@router.post("/coach/groups/{group_id}/athletes")
def assign_coach_group_athlete(
    group_id: str, req: CoachGroupAthleteRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    allowed = coach_groups.assign_athlete(tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id, group_id=group_id, athlete_id=req.athlete_id)
    if not allowed:
        raise HTTPException(status_code=404, detail="group or athlete not found in Coach scope")
    return {"assigned": True, "group_id": group_id, "athlete_id": req.athlete_id,
            "coach_final_authority": True, "execution_authorized": False}

@router.delete("/coach/groups/{group_id}/athletes/{athlete_id}")
def unassign_coach_group_athlete(
    group_id: str, athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    allowed = coach_groups.unassign_athlete(tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id, group_id=group_id, athlete_id=athlete_id)
    if not allowed:
        raise HTTPException(status_code=404, detail="group not found in Coach scope")
    return {"unassigned": True, "group_id": group_id, "athlete_id": athlete_id,
            "coach_final_authority": True, "execution_authorized": False}


# FEAT-004: lifecycle mutation and history are limited to verified Coach ownership.
class CoachAthleteStatusRequest(BaseModel):
    status: str
    reason: str

@router.patch("/coach/athletes/{athlete_id}/status")
def update_coach_athlete_status(
    athlete_id: str, req: CoachAthleteStatusRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    try:
        result = coach_roster.update_owned_athlete_status(
            tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
            athlete_id=athlete_id, new_status=req.status, reason=req.reason)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return {**result, "coach_final_authority": True, "execution_authorized": False}

@router.get("/coach/athletes/{athlete_id}/status-history")
def coach_athlete_status_history(
    athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    history = coach_roster.list_owned_athlete_status_history(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id)
    if history is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return {"athlete_id": athlete_id, "history": history,
            "total": len(history), "coach_final_authority": True,
            "execution_authorized": False}


# FEAT-005: read-only history over persisted decision/workflow records.
@router.get("/coach/athletes/{athlete_id}/decision-cycles")
def coach_athlete_decision_cycles(
    athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    cycles = coach_roster.list_owned_athlete_decision_cycles(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
        athlete_id=athlete_id)
    if cycles is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return {"athlete_id": athlete_id, "total": len(cycles), "cycles": cycles,
            "history_source": "existing_persisted_decision_and_training_records",
            "historical_backfill_performed": False,
            "coach_final_authority": True, "execution_authorized": False}


# FEAT-006: Coach home dashboard is a read-only aggregate of owned records.
@router.get("/coach/dashboard")
def coach_home_dashboard(
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    return coach_roster.get_coach_home_dashboard(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id)
