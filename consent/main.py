"""P14 child-data consent gate with optional durable PostgreSQL storage.

In-memory mode is permitted only when KAIZO_IDENTITY_MODE=development.
Production mode requires OIDC verification and PostgreSQL-backed consent/link
records. Guardian links must be established by a trusted onboarding process;
consent alone never creates a guardian relationship.
"""
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import jwt
import psycopg
from fastapi import FastAPI, Header, HTTPException
from jwt import PyJWKClient
from pydantic import BaseModel, Field

app = FastAPI(title="KAIZO P14 Minor/Child Consent Layer", version="1.1")


class ConsentState(str, Enum):
    pending = "pending"
    active = "active"
    revoked = "revoked"
    expired = "expired"


class Consent(BaseModel):
    child_id: str
    guardian_id: str
    academy_id: str
    resource: str
    action: str
    state: ConsentState
    expires_at: Optional[str] = None


class AccessRequest(BaseModel):
    child_id: str
    guardian_id: str
    academy_id: str
    resource: str
    action: str


class ConsentChange(BaseModel):
    consent: Consent
    actor_id: str = Field(min_length=1)


CONSENTS: list[Consent] = []
AUDIT: list[dict] = []


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identity_mode() -> str:
    return os.getenv("KAIZO_IDENTITY_MODE", "production").strip().lower()


def _postgres_enabled() -> bool:
    return os.getenv("KAIZO_PERSISTENCE_MODE", "memory").strip().lower() == "postgres"


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise HTTPException(status_code=503, detail="durable consent storage requires DATABASE_URL")
    return url


def _connect():
    return psycopg.connect(_database_url())


def _ensure_schema() -> None:
    """Verify the canonical Phase 4 schema exists; never create parallel ledgers."""
    if not _postgres_enabled():
        raise HTTPException(status_code=503, detail="durable consent storage is not enabled")
    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT to_regclass('public.kaizo_guardian_relationships'),
                              to_regclass('public.kaizo_p14_consents'),
                              to_regclass('public.kaizo_p14_audit_events')"""
                )
                tables = cur.fetchone()
        if not tables or any(table is None for table in tables):
            raise HTTPException(status_code=503, detail="canonical Phase 4 consent schema is unavailable")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="canonical Phase 4 consent schema is unavailable") from exc


def _verified_claims(authorization: str | None) -> dict:
    mode = _identity_mode()
    if mode == "development":
        # Explicitly unverified local test mode; never use for production.
        return {"development_unverified": True}
    if mode not in {"oidc", "oauth2", "external"}:
        raise HTTPException(status_code=503, detail="production consent identity is fail-closed")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Bearer authentication is required")
    token = authorization[7:].strip()
    issuer = os.getenv("KAIZO_OIDC_ISSUER", "").strip()
    audience = os.getenv("KAIZO_OIDC_AUDIENCE", "").strip()
    jwks_url = os.getenv("KAIZO_OIDC_JWKS_URL", "").strip()
    if not token or not issuer or not audience or not jwks_url:
        raise HTTPException(status_code=503, detail="OIDC provider configuration is incomplete")
    try:
        signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, signing_key.key, algorithms=["RS256"],
            audience=audience, issuer=issuer,
            options={"require": ["sub", "iss", "aud", "exp"]},
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="OIDC token verification failed") from exc
    role = claims.get("kaizo_role") or claims.get("role")
    tenant_id = claims.get("tenant_id") or claims.get("kaizo_tenant_id")
    if not claims.get("sub") or not role or not tenant_id:
        raise HTTPException(status_code=403, detail="verified identity lacks required KAIZO claims")
    return {"sub": str(claims["sub"]), "role": str(role), "tenant_id": str(tenant_id)}


def _require_guardian_actor(claims: dict, guardian_id: str, academy_id: str) -> None:
    if claims.get("development_unverified"):
        return
    if claims.get("role") != "parent" or claims.get("sub") != guardian_id:
        raise HTTPException(status_code=403, detail="verified guardian identity is required")
    if claims.get("tenant_id") != academy_id:
        raise HTTPException(status_code=403, detail="cross-tenant consent access denied")


def _audit(event: str, payload: dict) -> None:
    entry = {"event": event, "timestamp": _now(), **payload}
    AUDIT.append(entry)
    if _postgres_enabled():
        try:
            _ensure_schema()
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO kaizo_p14_audit_events
                           (actor_subject_id,event_type,child_resource_id,guardian_subject_id,
                            tenant_id,resource_type,action,allowed,reason_code,metadata)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                        (payload.get("actor_id"), event, payload.get("child_id"), payload.get("guardian_id"),
                         payload.get("academy_id"), payload.get("resource"), payload.get("action"),
                         payload.get("allowed"), payload.get("reason", event),
                         psycopg.types.json.Jsonb(payload)),
                    )
        except Exception as exc:
            raise HTTPException(status_code=503, detail="consent audit persistence failed") from exc


def valid(c: Consent, r: AccessRequest) -> tuple[bool, str]:
    if c.child_id != r.child_id: return False, "child_mismatch"
    if c.guardian_id != r.guardian_id: return False, "guardian_mismatch"
    if c.academy_id != r.academy_id: return False, "academy_mismatch"
    if c.resource != r.resource or c.action != r.action: return False, "scope_mismatch"
    if c.state != ConsentState.active: return False, f"consent_{c.state.value}"
    if c.expires_at:
        try:
            expiry = datetime.fromisoformat(c.expires_at.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                return False, "consent_expired"
        except ValueError:
            return False, "invalid_expiry"
    return True, "active_consent"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "kaizo-p14-consent",
        "deny_by_default": True,
        "durable_storage": _postgres_enabled(),
        "identity_mode": _identity_mode(),
    }


@app.post("/api/v1/consents")
def upsert_consent(
    change: ConsentChange,
    authorization: str | None = Header(None, alias="Authorization"),
):
    claims = _verified_claims(authorization)
    consent = change.consent
    _require_guardian_actor(claims, consent.guardian_id, consent.academy_id)
    if not change.actor_id.strip():
        raise HTTPException(status_code=400, detail="actor_id is required")

    if _postgres_enabled():
        _ensure_schema()
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT 1 FROM kaizo_guardian_relationships
                           WHERE guardian_subject_id=%s AND child_resource_id=%s AND tenant_id=%s
                             AND verification_status='VERIFIED'
                             AND verified_by_subject IS NOT NULL
                             AND verified_by_subject <> guardian_subject_id
                             AND verified_at IS NOT NULL
                             AND NOT EXISTS (
                               SELECT 1 FROM kaizo_guardian_relationships newer
                               WHERE newer.child_resource_id=kaizo_guardian_relationships.child_resource_id
                                 AND newer.guardian_subject_id=kaizo_guardian_relationships.guardian_subject_id
                                 AND newer.tenant_id=kaizo_guardian_relationships.tenant_id
                                 AND newer.recorded_sequence > kaizo_guardian_relationships.recorded_sequence
                             )
                           LIMIT 1""",
                        (consent.guardian_id, consent.child_id, consent.academy_id),
                    )
                    if not cur.fetchone():
                        raise HTTPException(status_code=403, detail="verified guardian-child link is required")
                    cur.execute(
                        """INSERT INTO kaizo_p14_consents
                           (child_resource_id,guardian_subject_id,tenant_id,resource_type,action,
                            state,expires_at,recorded_by_subject)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (consent.child_id, consent.guardian_id, consent.academy_id,
                         consent.resource, consent.action, consent.state.value,
                         consent.expires_at, claims.get("sub", change.actor_id)),
                    )
                    cur.execute(
                        """INSERT INTO kaizo_p14_audit_events
                           (actor_subject_id,event_type,child_resource_id,guardian_subject_id,
                            tenant_id,resource_type,action,allowed,reason_code,metadata)
                           VALUES (%s,'consent_change',%s,%s,%s,%s,%s,NULL,'consent_changed',%s::jsonb)""",
                        (claims.get("sub", change.actor_id), consent.child_id, consent.guardian_id,
                         consent.academy_id, consent.resource, consent.action,
                         psycopg.types.json.Jsonb({
                            "actor_id": claims.get("sub", change.actor_id),
                            "child_id": consent.child_id, "guardian_id": consent.guardian_id,
                            "academy_id": consent.academy_id, "resource": consent.resource,
                            "action": consent.action, "state": consent.state.value,
                         })),
                    )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="consent could not be durably stored") from exc
    else:
        if _identity_mode() != "development":
            raise HTTPException(status_code=503, detail="production consent requires durable PostgreSQL storage")
        CONSENTS[:] = [
            c for c in CONSENTS
            if not (c.child_id == consent.child_id and c.guardian_id == consent.guardian_id
                    and c.academy_id == consent.academy_id and c.resource == consent.resource
                    and c.action == consent.action)
        ]
        CONSENTS.append(consent)

    # PostgreSQL mode already wrote this event in the same transaction as the
    # consent upsert. Do not emit a second, non-atomic duplicate audit record.
    if not _postgres_enabled():
        _audit("consent_change", {
            "actor_id": claims.get("sub", change.actor_id), "child_id": consent.child_id,
            "guardian_id": consent.guardian_id, "academy_id": consent.academy_id,
            "resource": consent.resource, "action": consent.action, "state": consent.state.value,
        })
    return {"stored": True, "state": consent.state.value, "durable": _postgres_enabled()}


@app.post("/api/v1/authorize-child-data")
def authorize(
    req: AccessRequest,
    authorization: str | None = Header(None, alias="Authorization"),
):
    claims = _verified_claims(authorization)
    _require_guardian_actor(claims, req.guardian_id, req.academy_id)
    if _postgres_enabled():
        _ensure_schema()
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT 1 FROM kaizo_guardian_relationships
                           WHERE guardian_subject_id=%s AND child_resource_id=%s AND tenant_id=%s
                             AND verification_status='VERIFIED'
                             AND verified_by_subject IS NOT NULL
                             AND verified_by_subject <> guardian_subject_id
                             AND verified_at IS NOT NULL
                             AND NOT EXISTS (
                               SELECT 1 FROM kaizo_guardian_relationships newer
                               WHERE newer.child_resource_id=kaizo_guardian_relationships.child_resource_id
                                 AND newer.guardian_subject_id=kaizo_guardian_relationships.guardian_subject_id
                                 AND newer.tenant_id=kaizo_guardian_relationships.tenant_id
                                 AND newer.recorded_sequence > kaizo_guardian_relationships.recorded_sequence
                             )
                           LIMIT 1""",
                        (req.guardian_id, req.child_id, req.academy_id),
                    )
                    linked = cur.fetchone()
                    cur.execute(
                        """SELECT state,expires_at FROM kaizo_p14_consents
                           WHERE child_resource_id=%s AND guardian_subject_id=%s AND tenant_id=%s
                             AND resource_type=%s AND action=%s
                           ORDER BY recorded_sequence DESC LIMIT 1""",
                        (req.child_id, req.guardian_id, req.academy_id, req.resource, req.action),
                    )
                    row = cur.fetchone()
        except Exception as exc:
            raise HTTPException(status_code=503, detail="durable consent could not be verified") from exc
        if not linked:
            allowed, reason = False, "guardian_link_missing"
        elif not row:
            allowed, reason = False, "no_consent"
        else:
            state, expires_at = row
            try:
                consent = Consent(
                    child_id=req.child_id, guardian_id=req.guardian_id, academy_id=req.academy_id,
                    resource=req.resource, action=req.action, state=ConsentState(str(state).lower()),
                    expires_at=(expires_at.isoformat() if hasattr(expires_at, "isoformat") else expires_at),
                )
            except (ValueError, TypeError):
                # Corrupt or unknown persisted state must never authorize access.
                allowed, reason = False, "invalid_consent_state"
            else:
                allowed, reason = valid(consent, req)
    else:
        if _identity_mode() != "development":
            raise HTTPException(status_code=503, detail="production consent requires durable PostgreSQL storage")
        matches = [
            c for c in CONSENTS
            if c.child_id == req.child_id and c.guardian_id == req.guardian_id
            and c.academy_id == req.academy_id and c.resource == req.resource and c.action == req.action
        ]
        if not matches:
            allowed, reason = False, "no_consent"
        else:
            allowed, reason = valid(matches[-1], req)

    event = {
        # Persist the verified subject, never a caller-supplied actor identity.
        "actor_id": claims.get("sub", "development-unverified"),
        "child_id": req.child_id, "guardian_id": req.guardian_id, "academy_id": req.academy_id,
        "resource": req.resource, "action": req.action, "allowed": allowed, "reason": reason,
    }
    _audit("child_data_authorization", event)
    return {"allowed": allowed, "reason": reason, "coach_final_authority": True, "p13_rbac_required": True}


@app.get("/api/v1/audit")
def audit_log(authorization: str | None = Header(None, alias="Authorization")):
    claims = _verified_claims(authorization)
    if not claims.get("development_unverified") and claims.get("role") not in {"academy", "parent"}:
        raise HTTPException(status_code=403, detail="role cannot inspect consent audit")
    if _postgres_enabled():
        _ensure_schema()
        try:
            with _connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("""SELECT event_type,occurred_at,actor_subject_id,child_resource_id,
                                           guardian_subject_id,tenant_id,resource_type,action,
                                           allowed,reason_code,trace_id,metadata
                                    FROM kaizo_p14_audit_events
                                    WHERE tenant_id=%s
                                    ORDER BY occurred_at""", (claims.get("tenant_id"),))
                    events = [
                        {"event": event, "timestamp": timestamp, "actor_id": actor,
                         "child_id": child, "guardian_id": guardian, "academy_id": tenant,
                         "resource": resource, "action": action, "allowed": allowed,
                         "reason": reason, "trace_id": trace, **(metadata or {})}
                        for event, timestamp, actor, child, guardian, tenant, resource,
                            action, allowed, reason, trace, metadata in cur.fetchall()
                    ]
            return {"events": events, "durable": True}
        except Exception as exc:
            raise HTTPException(status_code=503, detail="consent audit is unavailable") from exc
    return {"events": AUDIT, "durable": False}


@app.get("/api/v1/policy")
def policy():
    return {
        "deny_by_default": True,
        "consent_is_scope_specific": True,
        "guardian_role_alone_is_insufficient": True,
        "p13_rbac_separate": True,
        "p05_persistence_separate": True,
        "production_requires_oidc_and_postgres": True,
        "guardian_link_must_be_preverified": True,
    }
