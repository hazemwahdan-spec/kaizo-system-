"""Commercial product API surface for KAIZO Phase 7."""
from typing import Any, Dict, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .product_surface import ProductSurface
from .runtime_adapter import ProductCoreRuntimeAdapter, RuntimeAuthorizationError, RuntimeContext
from .identity import IdentityNotConfiguredError, resolve_principal, resolve_bearer_principal, verify_bearer_token
import persistence

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
        context = ctx(actor_id, role, tenant_id, owner, authorization)
        verified_principal = None
        if authorization:
            # Bind caller headers to verified claims before processing or logging.
            try:
                verified_principal = resolve_bearer_principal(authorization)
            except IdentityNotConfiguredError as exc:
                raise HTTPException(status_code=401, detail="Verified OIDC identity required.") from exc
            if (
                verified_principal.actor_id != context.actor_id
                or verified_principal.role != context.role
                or verified_principal.tenant_id != context.tenant_id
            ):
                raise HTTPException(status_code=403, detail="Caller headers do not match verified identity.")
            if not persistence.is_postgres_enabled():
                raise HTTPException(
                    status_code=503,
                    detail="Durable tenant-scoped action history is required for authenticated Coach decisions.",
                )

        result = get_surface().request_decision(
            context, req.resource_tenant_id, req.model_dump(exclude={"resource_tenant_id"})
        )
        if verified_principal is not None:
            from datetime import datetime, timezone
            try:
                persistence.append_tenant_audit(
                    tenant_id=verified_principal.tenant_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    who=verified_principal.actor_id,
                    action="COACH_DECISION_REQUESTED",
                    old_value=None,
                    new_value={"case_id": req.case_id, "status": "decision_requested"},
                    why="Verified Coach requested a Core decision; execution remains unauthorized.",
                )
            except Exception as exc:
                # A decision must not be reported as successful when its required audit
                # record could not be durably written.
                raise HTTPException(
                    status_code=503,
                    detail="Durable tenant-scoped action history could not be recorded.",
                ) from exc
        return result
    except RuntimeAuthorizationError as exc:
        deny(exc)
    except (RuntimeError, persistence.PersistenceConfigurationError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Durable tenant-scoped action history could not be recorded.",
        ) from exc


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



@router.get("/coach/actions")
def coach_actions(
    limit: int = 50,
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Return only the authenticated Coach's own durable, tenant-scoped audit events.

    Caller-supplied actor/role/tenant headers are intentionally not used here.
    Legacy unscoped events and other actors' events are excluded.
    """
    try:
        principal = resolve_bearer_principal(authorization)
    except IdentityNotConfiguredError as exc:
        raise HTTPException(
            status_code=401,
            detail="A valid OIDC identity is required to read Coach action history.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    if not principal.verified or principal.source != "oidc_jwt":
        raise HTTPException(status_code=401, detail="Verified OIDC identity required.")
    if principal.role != "coach":
        raise HTTPException(status_code=403, detail="Coach role required.")
    if not isinstance(principal.tenant_id, str) or not principal.tenant_id.strip():
        raise HTTPException(status_code=403, detail="Tenant scope is required.")
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100.")
    if not persistence.is_postgres_enabled():
        raise HTTPException(
            status_code=503,
            detail="Durable tenant-scoped action history is not configured.",
        )
    try:
        records = persistence.list_tenant_audit_logs(tenant_id=principal.tenant_id)
    except (RuntimeError, persistence.PersistenceConfigurationError) as exc:
        raise HTTPException(
            status_code=503,
            detail="Durable tenant-scoped action history is unavailable.",
        ) from exc

    own_actions = [
        {
            "timestamp": record.get("timestamp"),
            "action": record.get("action"),
            "why": record.get("why"),
        }
        for record in records
        if record.get("who") == principal.actor_id
    ]
    return {
        "actor_id": principal.actor_id,
        "tenant_id": principal.tenant_id,
        "source": "durable_tenant_scoped_audit",
        "count": min(len(own_actions), limit),
        "actions": own_actions[-limit:],
        "execution_authorized": False,
    }
