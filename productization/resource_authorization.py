"""Canonical Phase 4 DB-backed tenant, guardian and P14 consent checks.

This module intentionally uses the canonical schema owned by the Phase 4
migration: kaizo_resource_tenant_bindings, kaizo_guardian_relationships,
kaizo_p14_consents. It must not create parallel authorization/consent ledgers.
All checks fail closed when PostgreSQL or canonical records are unavailable.
"""
from __future__ import annotations

from datetime import datetime, timezone

import persistence


class ResourceAuthorizationError(PermissionError):
    """The requested resource is not authorized."""


class ResourceAuthorizationUnavailable(RuntimeError):
    """Durable authorization data could not be verified."""


def _require_postgres() -> None:
    if not persistence.is_postgres_enabled():
        raise ResourceAuthorizationUnavailable(
            "canonical Phase 4 tenant/consent authorization requires PostgreSQL"
        )


def require_athlete_academy(athlete_id: str, academy_id: str) -> None:
    """Require a canonical server-side athlete-to-tenant resource binding."""
    if not athlete_id or not academy_id:
        raise ResourceAuthorizationError("athlete and academy are required")
    _require_postgres()
    try:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_resource_tenant_bindings
                       WHERE resource_type='athlete' AND resource_id=%s
                         AND tenant_id=%s LIMIT 1""",
                    (athlete_id, academy_id),
                )
                found = cur.fetchone()
    except Exception as exc:
        raise ResourceAuthorizationUnavailable(
            "could not verify canonical athlete-to-tenant binding"
        ) from exc
    if not found:
        raise ResourceAuthorizationError("athlete is not bound to this academy")


def require_parent_consent(
    guardian_id: str,
    athlete_id: str,
    academy_id: str,
    resource: str = "athlete_progress",
    action: str = "read",
) -> None:
    """Require a verified guardian relationship and latest exact-scope consent."""
    if not guardian_id or not athlete_id or not academy_id or not resource or not action:
        raise ResourceAuthorizationError(
            "verified guardian, athlete, academy and exact consent scope are required"
        )
    _require_postgres()
    try:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT 1 FROM kaizo_guardian_relationships gr
                       WHERE gr.guardian_subject_id=%s
                         AND gr.child_resource_id=%s AND gr.tenant_id=%s
                         AND gr.verification_status='VERIFIED'
                         AND gr.verified_by_subject IS NOT NULL
                         AND gr.verified_by_subject <> gr.guardian_subject_id
                         AND gr.verified_at IS NOT NULL
                         AND NOT EXISTS (
                           SELECT 1 FROM kaizo_guardian_relationships newer
                           WHERE newer.child_resource_id=gr.child_resource_id
                             AND newer.guardian_subject_id=gr.guardian_subject_id
                             AND newer.tenant_id=gr.tenant_id
                             AND newer.recorded_sequence > gr.recorded_sequence
                         )
                       LIMIT 1""",
                    (guardian_id, athlete_id, academy_id),
                )
                linked = cur.fetchone()
                if not linked:
                    consent = None
                else:
                    cur.execute(
                        """SELECT c.state, c.expires_at
                           FROM kaizo_p14_consents c
                           WHERE c.child_resource_id=%s
                             AND c.guardian_subject_id=%s AND c.tenant_id=%s
                             AND c.resource_type=%s AND c.action=%s
                             AND c.recorded_by_subject=c.guardian_subject_id
                             AND c.state='active'
                             AND (c.expires_at IS NULL OR c.expires_at > NOW())
                             AND NOT EXISTS (
                               SELECT 1 FROM kaizo_p14_consents newer
                               WHERE newer.child_resource_id=c.child_resource_id
                                 AND newer.guardian_subject_id=c.guardian_subject_id
                                 AND newer.tenant_id=c.tenant_id
                                 AND newer.resource_type=c.resource_type
                                 AND newer.action=c.action
                                 AND newer.recorded_sequence > c.recorded_sequence
                             )
                           ORDER BY c.recorded_sequence DESC LIMIT 1""",
                        (athlete_id, guardian_id, academy_id, resource, action),
                    )
                    consent = cur.fetchone()
    except Exception as exc:
        raise ResourceAuthorizationUnavailable(
            "could not verify canonical guardian relationship and durable P14 consent"
        ) from exc

    if not linked:
        raise ResourceAuthorizationError("verified guardian-to-child relationship is required")
    if not consent:
        raise ResourceAuthorizationError(
            "latest canonical P14 consent is absent, revoked, expired or out of scope"
        )
    state, expires_at = consent
    if str(state).lower() != "active":
        raise ResourceAuthorizationError(f"parental consent is not active: {state}")
    if expires_at:
        try:
            expiry = expires_at
            if isinstance(expiry, str):
                expiry = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= datetime.now(timezone.utc):
                raise ResourceAuthorizationError("parental consent has expired")
        except (ValueError, TypeError) as exc:
            raise ResourceAuthorizationError("parental consent expiry is invalid") from exc
