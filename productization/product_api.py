"""Commercial product API surface for KAIZO Phase 7."""
from typing import Any, Dict, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .product_surface import ProductSurface
from .runtime_adapter import ProductCoreRuntimeAdapter, RuntimeAuthorizationError, RuntimeContext
from .identity import IdentityNotConfiguredError, resolve_principal, resolve_bearer_principal, verify_bearer_token
from . import coach_roster, coach_groups, coach_priority_queue, coach_decision_workspace, coach_action_history, coach_audit_review, coach_product_action_traceability, coach_decision_cycles

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
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    # In OIDC mode, ctx derives role and tenant from the verified bearer token.
    # Client identity headers remain optional development-only scaffolding.
    try:
        return get_surface().navigation(
            ctx(actor_id or "", role or "", tenant_id or "", owner, authorization)
        )
    except RuntimeAuthorizationError as exc:
        deny(exc)


class DecisionRequest(BaseModel):
    resource_tenant_id: str
    athlete_id: str
    case_id: str
    decision: Dict[str, Any]
    intervention: Dict[str, Any]
    response_kpi: Dict[str, Any]
    retest: Dict[str, Any]


def _verified_owned_coach_athlete(authorization, actor_id, role, tenant_id, owner, athlete_id):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    athlete = coach_roster.get_owned_athlete(
        tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id,
        athlete_id=athlete_id,
    )
    if athlete is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return principal


@router.post("/decision")
def decision(
    req: DecisionRequest,
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _verified_owned_coach_athlete(
        authorization, actor_id, role, tenant_id, owner, req.athlete_id
    )
    try:
        context = RuntimeContext(
            actor_id=principal.actor_id, role=principal.role,
            tenant_id=principal.tenant_id, resource_owner_id=req.athlete_id,
        )
        decision_input = req.model_dump(exclude={"resource_tenant_id"})
        decision_output = get_surface().request_decision(
            context, req.resource_tenant_id, decision_input,
        )
        cycle = coach_decision_cycles.create_cycle(
            tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
            athlete_id=req.athlete_id, case_id=req.case_id,
            decision_input=decision_input,
            decision_output=decision_output if isinstance(decision_output, dict)
                            else {"result": decision_output},
        )
        if isinstance(decision_output, dict):
            return {**decision_output, "decision_cycle_id": cycle["decision_cycle_id"],
                    "decision_cycle_version": cycle["version"]}
        return {"result": decision_output, "decision_cycle_id": cycle["decision_cycle_id"],
                "decision_cycle_version": cycle["version"]}
    except RuntimeAuthorizationError as exc:
        deny(exc)


def _verified_owned_coach_cycle(principal, athlete_id, decision_cycle_id, case_id):
    if not str(decision_cycle_id or "").strip():
        raise HTTPException(status_code=422, detail="decision_cycle_id is required for adaptation")
    cycle = coach_decision_cycles.get_owned_cycle(
        decision_cycle_id=decision_cycle_id, tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id, athlete_id=athlete_id,
    )
    if cycle is None:
        raise HTTPException(status_code=404, detail="decision cycle not found in Coach athlete scope")
    if cycle["case_id"] != case_id:
        raise HTTPException(status_code=409, detail="case_id does not match the persisted decision cycle")
    return cycle


class AdaptationRequest(BaseModel):
    resource_tenant_id: str
    athlete_id: str
    decision_cycle_id: str
    decision_id: str | None = None
    case_id: str
    operation: str
    common_core: Dict[str, Any]
    dynamic_inputs: Dict[str, Any]
    individual_change: Dict[str, Any] | None = None
    team_change: Dict[str, Any] | None = None
    composition_change: Dict[str, Any] | None = None


@router.post("/adaptation")
def adaptation(
    req: AdaptationRequest,
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _verified_owned_coach_athlete(
        authorization, actor_id, role, tenant_id, owner, req.athlete_id
    )
    cycle = _verified_owned_coach_cycle(
        principal, req.athlete_id, req.decision_cycle_id, req.case_id
    )
    try:
        context = RuntimeContext(
            actor_id=principal.actor_id, role=principal.role,
            tenant_id=principal.tenant_id, resource_owner_id=req.athlete_id,
        )
        adaptation_input = req.model_dump(exclude={
            "resource_tenant_id", "decision_id", "decision_cycle_id"
        })
        adaptation_input["decision_id"] = req.decision_cycle_id
        adaptation_output = get_surface().adapt_decision(
            context, req.resource_tenant_id, adaptation_input,
        )
        cycle = coach_decision_cycles.record_adaptation(
            decision_cycle_id=req.decision_cycle_id,
            tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id,
            athlete_id=req.athlete_id,
            adaptation_input={**adaptation_input, "decision_cycle_id": req.decision_cycle_id},
            adaptation_output=adaptation_output if isinstance(adaptation_output, dict)
                              else {"result": adaptation_output},
        )
        if cycle is None:
            raise HTTPException(status_code=404, detail="decision cycle not found in Coach athlete scope")
        if isinstance(adaptation_output, dict):
            return {**adaptation_output, "decision_cycle_id": cycle["decision_cycle_id"],
                    "decision_cycle_version": cycle["version"]}
        return {"result": adaptation_output, "decision_cycle_id": cycle["decision_cycle_id"],
                "decision_cycle_version": cycle["version"]}
    except RuntimeAuthorizationError as exc:
        deny(exc)


class InterventionRequest(DecisionRequest):
    coach_approved: bool = False


@router.post("/intervention")
def intervention(
    req: InterventionRequest,
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _verified_owned_coach_athlete(
        authorization, actor_id, role, tenant_id, owner, req.athlete_id
    )
    try:
        context = RuntimeContext(
            actor_id=principal.actor_id, role=principal.role,
            tenant_id=principal.tenant_id, resource_owner_id=req.athlete_id,
            coach_approved=req.coach_approved,
        )
        return get_surface().record_intervention(
            context, req.resource_tenant_id,
            req.model_dump(exclude={"resource_tenant_id", "coach_approved"}),
        )
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


# FEAT-007: evidence-backed, read-only Coach current-priority queue.
@router.get("/coach/priority-queue")
def coach_priority_queue_read(
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    return coach_priority_queue.get_coach_priority_queue(
        tenant_id=principal.tenant_id, coach_actor_id=principal.actor_id)


# FEAT-009: read-only, ownership-scoped Coach decision-cycle workspace.
@router.get("/coach/athletes/{athlete_id}/decision-workspace")
def coach_decision_workspace_read(
    athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    result = coach_decision_workspace.get_coach_decision_workspace(
        tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id,
        athlete_id=athlete_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return {"athlete_id": athlete_id, **result}


# FEAT-010: verified Coach action history; read-only and tenant/actor scoped.
@router.get("/coach/athletes/{athlete_id}/action-history")
def coach_action_history_read(
    athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    result = coach_action_history.get_coach_action_history(
        tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id,
        athlete_id=athlete_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return {"athlete_id": athlete_id, **result}


# FEAT-054: read-only audit query over the already verified Coach action-history boundary.
@router.get("/coach/athletes/{athlete_id}/audit-review")
def coach_audit_review_read(
    athlete_id: str,
    query: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    try:
        result = coach_audit_review.review_coach_audit(
            tenant_id=principal.tenant_id,
            coach_actor_id=principal.actor_id,
            athlete_id=athlete_id,
            query=query,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return result


# FEAT-055: product-action traceability links only verified source IDs from
# the authenticated Coach's own tenant-scoped athlete history.
class CoachProductActionTraceRequest(BaseModel):
    product_action: str
    source_record_ids: List[str]
    trace_reason: str


@router.post("/coach/athletes/{athlete_id}/product-action-traces", status_code=201)
def create_coach_product_action_trace(
    athlete_id: str,
    req: CoachProductActionTraceRequest,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    try:
        result = coach_product_action_traceability.create_coach_product_action_trace(
            tenant_id=principal.tenant_id,
            coach_actor_id=principal.actor_id,
            athlete_id=athlete_id,
            product_action=req.product_action,
            source_record_ids=req.source_record_ids,
            trace_reason=req.trace_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    if not result.get("created"):
        raise HTTPException(status_code=503, detail={
            "status": result.get("status", "INSUFFICIENT_EVIDENCE"),
            "message": result.get("message", "trace evidence unavailable"),
        })
    return result


@router.get("/coach/athletes/{athlete_id}/product-action-traces")
def list_coach_product_action_traces(
    athlete_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
    actor_id: str | None = Header(None, alias="X-KAIZO-Actor"),
    role: str | None = Header(None, alias="X-KAIZO-Role"),
    tenant_id: str | None = Header(None, alias="X-KAIZO-Tenant"),
    owner: str | None = Header(None, alias="X-KAIZO-Resource-Owner"),
):
    principal = _coach_scope(authorization, actor_id, role, tenant_id, owner)
    result = coach_product_action_traceability.list_coach_product_action_traces(
        tenant_id=principal.tenant_id,
        coach_actor_id=principal.actor_id,
        athlete_id=athlete_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="athlete not found in Coach scope")
    return result
