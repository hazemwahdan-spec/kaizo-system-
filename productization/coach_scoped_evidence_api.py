"""Authenticated Product API for Coach-scoped evidence, knowledge and governance.

All identities are derived from a verified OIDC Bearer token. This router only
exposes the additive PostgreSQL service; legacy unscoped routers remain retired.
"""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

import persistence
import coach_scoped_evidence_runtime as evidence_service
from productization.identity import IdentityNotConfiguredError, resolve_bearer_principal

router = APIRouter(prefix="/api/v1/product", tags=["Coach Evidence & Governance"])


def _principal(authorization: str | None):
    try:
        principal = resolve_bearer_principal(authorization)
    except IdentityNotConfiguredError as exc:
        raise HTTPException(status_code=401, detail="verified OIDC Bearer token required") from exc
    if (principal.verified is not True or principal.source != "oidc_jwt"
            or principal.role != "coach" or "product" not in principal.permissions):
        raise HTTPException(status_code=403, detail="verified OIDC Coach with Product permission required")
    if not persistence.is_postgres_enabled():
        raise HTTPException(status_code=503, detail="durable PostgreSQL persistence is required")
    return principal


def _service(call, **kwargs):
    try:
        return call(**kwargs)
    except evidence_service.CoachEvidenceAuthorizationError as exc:
        # Do not disclose whether a foreign athlete/resource exists.
        raise HTTPException(status_code=404, detail="resource not found in authenticated Coach scope") from exc
    except evidence_service.CoachEvidenceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Coach evidence persistence is unavailable") from exc


class ProvenanceCreate(BaseModel):
    knowledge_id: str = Field(min_length=1, max_length=160)
    source_type: str = Field(min_length=1, max_length=80)
    source_ref: str = Field(min_length=1, max_length=500)
    source_version: str = Field(min_length=1, max_length=120)
    provenance_note: str = Field(min_length=1, max_length=4000)
    evidence_refs: list[str] = Field(min_length=1, max_length=50)


class LifecycleChange(BaseModel):
    target_status: str
    expected_version: int = Field(ge=1)


class KnowledgeLinkCreate(BaseModel):
    knowledge_id: str
    link_type: str = Field(min_length=1, max_length=80)
    evidence_refs: list[str] = Field(min_length=1, max_length=50)


class ActorTraceCreate(BaseModel):
    action: str = Field(min_length=1, max_length=160)
    evidence_refs: list[str] = Field(default_factory=list, max_length=50)
    correlation_id: str | None = Field(default=None, max_length=160)


class GovernanceWrite(BaseModel):
    resource_type: str
    resource_id: str
    governance_status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = Field(default=None, ge=1)


@router.post("/coach/athletes/{athlete_id}/knowledge", status_code=201)
def create_knowledge_provenance(
    athlete_id: str, req: ProvenanceCreate,
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _principal(authorization)
    return _service(evidence_service.record_provenance, principal=principal,
        athlete_id=athlete_id, **req.model_dump())


@router.patch("/coach/athletes/{athlete_id}/knowledge/{knowledge_id}/lifecycle")
def update_knowledge_lifecycle(
    athlete_id: str, knowledge_id: str, req: LifecycleChange,
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _principal(authorization)
    return _service(evidence_service.change_lifecycle, principal=principal,
        athlete_id=athlete_id, knowledge_id=knowledge_id, **req.model_dump())


@router.get("/coach/athletes/{athlete_id}/knowledge")
def retrieve_approved_knowledge(
    athlete_id: str, query: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _principal(authorization)
    records = _service(evidence_service.retrieve_knowledge, principal=principal,
        athlete_id=athlete_id, query=query, limit=limit)
    return {"athlete_id": athlete_id, "knowledge": records,
            "coach_final_authority": True, "execution_authorized": False}


@router.post("/coach/athletes/{athlete_id}/training-sessions/{session_id}/knowledge-links", status_code=201)
def link_knowledge_to_session(
    athlete_id: str, session_id: str, req: KnowledgeLinkCreate,
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _principal(authorization)
    return _service(evidence_service.link_training_session, principal=principal,
        athlete_id=athlete_id, session_id=session_id, **req.model_dump())


@router.post("/coach/athletes/{athlete_id}/actor-traces", status_code=201)
def create_actor_trace(
    athlete_id: str, req: ActorTraceCreate,
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _principal(authorization)
    return _service(evidence_service.record_actor_trace, principal=principal,
        athlete_id=athlete_id, **req.model_dump())


@router.get("/coach/athletes/{athlete_id}/actor-traces")
def list_actor_traces(
    athlete_id: str, limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _principal(authorization)
    tenant, actor = principal.tenant_id, principal.actor_id
    try:
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                evidence_service._lock_primary_owner(cur, tenant_id=tenant,
                    coach_actor_id=actor, athlete_id=athlete_id)
                cur.execute(
                    """SELECT trace_id,action,occurred_at,evidence_refs,correlation_id
                       FROM kaizo_coach_scoped_actor_trace
                       WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                       ORDER BY occurred_at DESC LIMIT %s""",
                    (tenant, actor, athlete_id, limit),
                )
                rows = cur.fetchall()
        return {"athlete_id": athlete_id, "traces": [
            {"trace_id": r[0], "action": r[1], "occurred_at": r[2],
             "evidence_refs": r[3], "correlation_id": r[4]} for r in rows
        ], "coach_final_authority": True, "execution_authorized": False}
    except evidence_service.CoachEvidenceAuthorizationError as exc:
        raise HTTPException(status_code=404, detail="athlete not found in authenticated Coach scope") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Coach trace persistence is unavailable") from exc


@router.put("/coach/athletes/{athlete_id}/governance")
def write_governance(
    athlete_id: str, req: GovernanceWrite,
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _principal(authorization)
    return _service(evidence_service.set_governance, principal=principal,
        athlete_id=athlete_id, **req.model_dump())


@router.get("/coach/athletes/{athlete_id}/governance/{resource_type}/{resource_id}")
def read_governance(
    athlete_id: str, resource_type: str, resource_id: str,
    authorization: str | None = Header(None, alias="Authorization"),
):
    principal = _principal(authorization)
    tenant, actor = principal.tenant_id, principal.actor_id
    try:
        with persistence.atomic_transaction() as conn:
            with conn.cursor() as cur:
                evidence_service._lock_primary_owner(cur, tenant_id=tenant,
                    coach_actor_id=actor, athlete_id=athlete_id)
                cur.execute(
                    """SELECT governance_id,governance_status,metadata,version,updated_at
                       FROM kaizo_coach_scoped_governance
                       WHERE tenant_id=%s AND coach_actor_id=%s AND athlete_id=%s
                         AND resource_type=%s AND resource_id=%s""",
                    (tenant, actor, athlete_id, resource_type, resource_id),
                )
                row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="governance record not found")
        return {"governance_id": row[0], "athlete_id": athlete_id,
            "resource_type": resource_type, "resource_id": resource_id,
            "governance_status": row[1], "metadata": row[2], "version": int(row[3]),
            "updated_at": row[4], "coach_final_authority": True, "execution_authorized": False}
    except evidence_service.CoachEvidenceAuthorizationError as exc:
        raise HTTPException(status_code=404, detail="athlete not found in authenticated Coach scope") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Coach governance persistence is unavailable") from exc
