"""Persistence primitives for Phase 4 identity and minor-consent records.

These functions are deliberately not wired to request routes. They only use
the existing PostgreSQL persistence connection; memory mode returns no
authorization proof. A route must deny access unless these lookups return True.
The migration must be applied explicitly to a test database before use.
"""
from __future__ import annotations

from typing import Any

import persistence


def _postgres_required() -> None:
    if not persistence.is_postgres_enabled():
        raise persistence.PersistenceConfigurationError(
            "Phase 4 identity/consent persistence requires PostgreSQL; "
            "memory mode is not an authorization source"
        )


def record_membership(
    *, membership_id: str, actor_id: str, academy_id: str, role: str,
    status: str, version: int, resource_owner_id: str | None = None,
) -> None:
    """Append a membership state/version; never treat client payload as identity."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_tenant_memberships
                   (membership_id, actor_id, academy_id, role, status, version, resource_owner_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (membership_id, actor_id, academy_id, role, status, version, resource_owner_id),
            )
        conn.commit()


def has_active_membership(*, actor_id: str, academy_id: str, role: str) -> bool:
    """Only the latest recorded version can grant membership."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT status FROM kaizo_tenant_memberships
                   WHERE actor_id=%s AND academy_id=%s AND role=%s
                   ORDER BY version DESC LIMIT 1""",
                (actor_id, academy_id, role),
            )
            row = cur.fetchone()
    return bool(row and row[0] == "active")


def record_guardian_relationship(
    *, relationship_id: str, child_id: str, guardian_actor_id: str,
    academy_id: str, verification_status: str, version: int,
    verified_by: str | None = None, verified_at: Any = None,
) -> None:
    """Append relationship state. This function does not verify the source of proof."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_guardian_relationships
                   (relationship_id, child_id, guardian_actor_id, academy_id,
                    verification_status, version, verified_by, verified_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (relationship_id, child_id, guardian_actor_id, academy_id,
                 verification_status, version, verified_by, verified_at),
            )
        conn.commit()


def has_verified_guardian_relationship(
    *, child_id: str, guardian_actor_id: str, academy_id: str,
) -> bool:
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT verification_status FROM kaizo_guardian_relationships
                   WHERE child_id=%s AND guardian_actor_id=%s AND academy_id=%s
                   ORDER BY version DESC LIMIT 1""",
                (child_id, guardian_actor_id, academy_id),
            )
            row = cur.fetchone()
    return bool(row and row[0] == "verified")


def record_child_consent(
    *, consent_id: str, child_id: str, guardian_actor_id: str,
    academy_id: str, resource: str, action: str, state: str,
    expires_at: Any, recorded_by_actor_id: str, version: int,
) -> None:
    """Append a consent state/version; expiration is mandatory and checked at read time."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_child_consents
                   (consent_id, child_id, guardian_actor_id, academy_id, resource,
                    action, state, expires_at, recorded_by_actor_id, version)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (consent_id, child_id, guardian_actor_id, academy_id, resource,
                 action, state, expires_at, recorded_by_actor_id, version),
            )
        conn.commit()


def has_active_child_consent(
    *, child_id: str, guardian_actor_id: str, academy_id: str,
    resource: str, action: str,
) -> bool:
    """Fail closed unless the latest exact-scope consent is active and unexpired."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT state, expires_at > NOW() AS unexpired
                   FROM kaizo_child_consents
                   WHERE child_id=%s AND guardian_actor_id=%s AND academy_id=%s
                     AND resource=%s AND action=%s
                   ORDER BY version DESC LIMIT 1""",
                (child_id, guardian_actor_id, academy_id, resource, action),
            )
            row = cur.fetchone()
    return bool(row and row[0] == "active" and row[1] is True)


def append_authorization_audit(
    *, event_id: str, correlation_id: str, actor_id: str,
    actor_role: str | None, academy_id: str | None,
    resource_type: str, resource_id: str | None, action: str,
    decision: str, reason_code: str, consent_id: str | None,
    policy_version: str, request_route: str,
) -> None:
    """Persist a minimal allow/deny event; callers must fail closed on write failure."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_authorization_audit
                   (event_id, correlation_id, actor_id, actor_role, academy_id,
                    resource_type, resource_id, action, decision, reason_code,
                    consent_id, policy_version, request_route)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (event_id, correlation_id, actor_id, actor_role, academy_id,
                 resource_type, resource_id, action, decision, reason_code,
                 consent_id, policy_version, request_route),
            )
        conn.commit()


def list_authorization_audit(*, correlation_id: str) -> list[dict[str, Any]]:
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT event_id, actor_id, decision, reason_code, resource_type,
                          resource_id, action, policy_version, request_route
                   FROM kaizo_authorization_audit
                   WHERE correlation_id=%s ORDER BY occurred_at, event_id""",
                (correlation_id,),
            )
            rows = cur.fetchall()
    return [
        {
            "event_id": row[0], "actor_id": row[1], "decision": row[2],
            "reason_code": row[3], "resource_type": row[4], "resource_id": row[5],
            "action": row[6], "policy_version": row[7], "request_route": row[8],
        }
        for row in rows
    ]


def bind_resource_to_tenant(
    *, resource_type: str, resource_id: str, tenant_id: str, bound_by_actor_id: str,
) -> None:
    """Create authoritative server-side tenant binding for a persisted resource."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_resource_tenant_bindings
                   (resource_type, resource_id, tenant_id, bound_by_actor_id)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (resource_type, resource_id) DO NOTHING""",
                (resource_type, resource_id, tenant_id, bound_by_actor_id),
            )
            cur.execute(
                """SELECT tenant_id FROM kaizo_resource_tenant_bindings
                   WHERE resource_type=%s AND resource_id=%s""",
                (resource_type, resource_id),
            )
            row = cur.fetchone()
            if not row or row[0] != tenant_id:
                raise persistence.PersistenceConfigurationError(
                    "Resource already has a different authoritative tenant binding"
                )
        conn.commit()


def get_resource_tenant(*, resource_type: str, resource_id: str) -> str | None:
    """Resolve tenant scope from the database; never from request payload."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT tenant_id FROM kaizo_resource_tenant_bindings
                   WHERE resource_type=%s AND resource_id=%s""",
                (resource_type, resource_id),
            )
            row = cur.fetchone()
    return str(row[0]) if row else None


def record_age_classification(
    *, athlete_id: str, academy_id: str, age_class: str, status: str,
    version: int, verified_by: str, verified_at: Any,
) -> None:
    """Append a trusted, versioned age classification; request payloads are not proof."""
    _postgres_required()
    if age_class not in {"adult", "minor"} or status not in {"verified", "revoked"}:
        raise ValueError("Invalid age classification state")
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_athlete_age_classifications
                   (athlete_id, academy_id, age_class, status, version, verified_by, verified_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                (athlete_id, academy_id, age_class, status, version, verified_by, verified_at),
            )
        conn.commit()


def get_verified_age_classification(*, athlete_id: str, academy_id: str) -> str | None:
    """Return only the latest verified classification; missing/revoked is unknown."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT age_class, status FROM kaizo_athlete_age_classifications
                   WHERE athlete_id=%s AND academy_id=%s
                   ORDER BY version DESC LIMIT 1""",
                (athlete_id, academy_id),
            )
            row = cur.fetchone()
    return str(row[0]) if row and row[1] == "verified" else None


def has_active_minor_consent(
    *, child_id: str, academy_id: str, resource: str, action: str,
) -> bool:
    """Require a latest verified guardian relationship and active, unexpired scoped consent."""
    _postgres_required()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """WITH latest_relationships AS (
                       SELECT DISTINCT ON (guardian_actor_id)
                              guardian_actor_id, verification_status
                       FROM kaizo_guardian_relationships
                       WHERE child_id=%s AND academy_id=%s
                       ORDER BY guardian_actor_id, version DESC
                   ), latest_consents AS (
                       SELECT DISTINCT ON (guardian_actor_id)
                              guardian_actor_id, state, expires_at
                       FROM kaizo_child_consents
                       WHERE child_id=%s AND academy_id=%s
                         AND resource=%s AND action=%s
                       ORDER BY guardian_actor_id, version DESC
                   )
                   SELECT EXISTS (
                       SELECT 1 FROM latest_relationships r
                       JOIN latest_consents c USING (guardian_actor_id)
                       WHERE r.verification_status='verified'
                         AND c.state='active' AND c.expires_at > NOW()
                   )""",
                (child_id, academy_id, child_id, academy_id, resource, action),
            )
            row = cur.fetchone()
    return bool(row and row[0])
