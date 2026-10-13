"""Commercial product API surface for KAIZO Phase 7."""
from typing import Any, Dict, List
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from .product_surface import ProductSurface
from .runtime_adapter import ProductCoreRuntimeAdapter, RuntimeAuthorizationError, RuntimeContext
from .identity import IdentityNotConfiguredError, resolve_principal, verify_bearer_token
from phase4_identity_store import has_active_child_consent, has_verified_guardian_relationship

router = APIRouter(prefix="/api/v1/product", tags=["Commercial Product"])


@router.get("/auth/oidc/verify")
def verify_oidc(
    authorization: str | None = Header(None, alias="Authorization"),
):
    """Live OIDC verification endpoint for standard JWT validation."""
    try:
        return verify_bearer_token(authorization)
    except IdentityNotConfiguredError:
        # Do not disclose issuer, audience, JWKS, or token-validation internals.
        raise HTTPException(status_code=401, detail="Invalid or unconfigured OIDC bearer token")

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
        # Never trust caller-supplied role/owner headers as proof of guardianship.
        # ctx() resolves the principal from the configured identity provider; in
        # production/OIDC mode the bearer token is mandatory and verified.
        principal = ctx(actor_id, role, tenant_id, owner, authorization)
        if principal.role != "parent":
            raise HTTPException(status_code=403, detail="only Parent may use linked-athlete view")
        if principal.tenant_id != resource_tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant access denied")
        if principal.resource_owner_id and principal.resource_owner_id != athlete_id:
            raise HTTPException(status_code=403, detail="explicit athlete linkage required")

        # The signed identity's optional resource_owner claim is not the source
        # of truth for parent-child linkage. Require the current durable guardian
        # relationship and exact-scope consent before any parent progress is read.
        try:
            linked = has_verified_guardian_relationship(
                child_id=athlete_id,
                guardian_actor_id=principal.actor_id,
                academy_id=resource_tenant_id,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Authoritative guardian relationship store is unavailable",
            ) from exc
        if not linked:
            raise HTTPException(status_code=403, detail="verified guardian relationship required")

        try:
            consent = has_active_child_consent(
                child_id=athlete_id,
                guardian_actor_id=principal.actor_id,
                academy_id=resource_tenant_id,
                resource="athlete_progress",
                action="read",
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Authoritative guardian consent store is unavailable",
            ) from exc
        if not consent:
            raise HTTPException(status_code=403, detail="active guardian consent for athlete progress is required")

        # Bind the already database-verified child to the product-surface scope.
        scoped_parent = RuntimeContext(
            actor_id=principal.actor_id,
            role=principal.role,
            tenant_id=principal.tenant_id,
            resource_owner_id=athlete_id,
        )
        return get_surface().parent_progress(scoped_parent, resource_tenant_id, athlete_id, [])
    except RuntimeAuthorizationError as exc:
        deny(exc)
