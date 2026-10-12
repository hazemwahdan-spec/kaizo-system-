"""Fail-closed repository for Phase 4 tenant, resource and P14 consent checks.

This module is intentionally not wired to API routes yet. Callers must pass a
principal created by the verified OIDC resolver; request-body actor IDs are not
identity. Missing PostgreSQL configuration denies access. Consent decisions and
their audit event are written in the same transaction.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import persistence


class Phase4AuthorizationUnavailable(RuntimeError):
    """Raised when durable authorization cannot be evaluated safely."""


def _verified_subject(principal: Any) -> str | None:
    # Align with productization.identity.Principal (verified/source/actor_id).
    # Mapping support exists for tests and resolver adapters, but the same
    # verified=True and source=oidc_jwt requirements always apply.
    if isinstance(principal, Mapping):
        verified = principal.get("verified") is True
        source = principal.get("source")
        subject = principal.get("actor_id") or principal.get("sub")
    else:
        verified = getattr(principal, "verified", False) is True
        source = getattr(principal, "source", None)
        subject = getattr(principal, "actor_id", None)
    if not verified or source != "oidc_jwt":
        return None
    if not isinstance(subject, str) or not subject.strip():
        return None
    return subject.strip()


def authorize_resource_access(
    *,
    principal: Mapping[str, Any],
    tenant_id: str,
    resource_type: str,
    resource_id: str,
    allowed_roles: Sequence[str],
    action: str,
    trace_id: str | None = None,
    child_resource_id: str | None = None,
    requires_guardian_consent: bool = False,
) -> dict[str, Any]:
    """Evaluate membership, server-side ownership and optional child consent.

    The principal must be output from the verified OIDC resolver. Tenant and
    resource identifiers are lookup keys only: authorization is based on
    persisted membership and resource bindings, never on request claims alone.
    The returned allowed value is advisory until real routes enforce it.
    """
    subject = _verified_subject(principal)
    if not subject:
        return {
            "allowed": False,
            "reason_code": "verified_oidc_principal_required",
            "trace_id": trace_id,
            "audit_persisted": False,
        }
    if not all(isinstance(v, str) and v.strip() for v in
               (tenant_id, resource_type, resource_id, action)):
        return {
            "allowed": False,
            "reason_code": "authorization_scope_incomplete",
            "trace_id": trace_id,
            "audit_persisted": False,
        }
    if requires_guardian_consent and not (
        isinstance(child_resource_id, str) and child_resource_id.strip()
    ):
        return {
            "allowed": False,
            "reason_code": "child_scope_required",
            "trace_id": trace_id,
            "audit_persisted": False,
        }
    if not persistence.is_postgres_enabled():
        raise Phase4AuthorizationUnavailable(
            "Durable Phase 4 authorization requires PostgreSQL mode"
        )

    allowed = False
    reason = "membership_missing_or_inactive"
    guardian_subject: str | None = None
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM kaizo_tenant_memberships
                   WHERE tenant_id=%s AND subject_id=%s AND role = ANY(%s)
                     AND status='ACTIVE' LIMIT 1""",
                (tenant_id, subject, list(allowed_roles)),
            )
            membership_ok = cur.fetchone() is not None
            if membership_ok:
                cur.execute(
                    """SELECT 1 FROM kaizo_resource_tenant_bindings
                       WHERE resource_type=%s AND resource_id=%s AND tenant_id=%s""",
                    (resource_type, resource_id, tenant_id),
                )
                binding_ok = cur.fetchone() is not None
                if not binding_ok:
                    reason = "resource_tenant_binding_missing_or_mismatched"
                elif requires_guardian_consent:
                    reason = "verified_guardian_or_active_consent_missing"
                    cur.execute(
                        """SELECT gr.guardian_subject_id
                           FROM kaizo_guardian_relationships gr
                           JOIN kaizo_p14_consents c
                             ON c.child_resource_id=gr.child_resource_id
                            AND c.guardian_subject_id=gr.guardian_subject_id
                            AND c.tenant_id=gr.tenant_id
                           WHERE gr.child_resource_id=%s
                             AND gr.tenant_id=%s
                             AND gr.verification_status='VERIFIED'
                             AND gr.verified_by_subject IS NOT NULL
                             AND gr.verified_at IS NOT NULL
                             AND NOT EXISTS (
                               SELECT 1 FROM kaizo_guardian_relationships newer_gr
                               WHERE newer_gr.child_resource_id=gr.child_resource_id
                                 AND newer_gr.guardian_subject_id=gr.guardian_subject_id
                                 AND newer_gr.tenant_id=gr.tenant_id
                                 AND newer_gr.created_at > gr.created_at
                             )
                             AND c.resource_type=%s AND c.action=%s
                             AND c.state='active'
                             AND (c.expires_at IS NULL OR c.expires_at > NOW())
                             AND NOT EXISTS (
                               SELECT 1 FROM kaizo_p14_consents newer
                               WHERE newer.child_resource_id=c.child_resource_id
                                 AND newer.guardian_subject_id=c.guardian_subject_id
                                 AND newer.tenant_id=c.tenant_id
                                 AND newer.resource_type=c.resource_type
                                 AND newer.action=c.action
                                 AND newer.created_at > c.created_at
                             )
                           ORDER BY c.created_at DESC LIMIT 1""",
                        (child_resource_id, tenant_id, resource_type, action),
                    )
                    row = cur.fetchone()
                    if row is not None:
                        guardian_subject = row[0]
                        allowed = True
                        reason = "verified_guardian_active_scoped_consent"
                else:
                    allowed = True
                    reason = "active_membership_and_resource_binding"

            cur.execute(
                """INSERT INTO kaizo_p14_audit_events
                   (actor_subject_id,event_type,child_resource_id,guardian_subject_id,
                    tenant_id,resource_type,action,allowed,reason_code,trace_id,metadata)
                   VALUES (%s,'authorization_decision',%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                (
                    subject, child_resource_id, guardian_subject, tenant_id,
                    resource_type, action, allowed, reason, trace_id,
                    '{"source":"phase4_tenant_consent_repository"}',
                ),
            )
    return {
        "allowed": allowed,
        "reason_code": reason,
        "tenant_id": tenant_id,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "subject_id": subject,
        "trace_id": trace_id,
        "audit_persisted": True,
        "coach_final_authority": True,
        "execution_authorized": False,
    }
