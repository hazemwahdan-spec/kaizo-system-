"""Additive Academy/Tenant/Coach membership contract.

This module is deliberately not mounted as an API router. Callers must first
resolve a verified OIDC Principal and enforce an Academy permission. It does
not change the existing single-primary-Coach ownership boundary.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import persistence


class AcademyContractConflict(ValueError):
    """The requested relationship conflicts with authoritative scope."""


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS kaizo_tenant_academies (
    academy_id TEXT PRIMARY KEY REFERENCES kaizo_academies(academy_id) ON DELETE RESTRICT,
    tenant_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE (tenant_id, academy_id)
);
CREATE INDEX IF NOT EXISTS idx_tenant_academies_scope
    ON kaizo_tenant_academies (tenant_id, status, academy_id);

CREATE TABLE IF NOT EXISTS kaizo_academy_coach_memberships (
    membership_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    academy_id TEXT NOT NULL,
    coach_actor_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('OWNER', 'ADMIN', 'HEAD_COACH', 'COACH', 'ASSISTANT')),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'REVOKED')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    UNIQUE (tenant_id, academy_id, coach_actor_id),
    UNIQUE (tenant_id, academy_id, membership_id),
    UNIQUE (tenant_id, academy_id, coach_actor_id, membership_id),
    FOREIGN KEY (tenant_id, academy_id)
        REFERENCES kaizo_tenant_academies (tenant_id, academy_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_academy_membership_actor_scope
    ON kaizo_academy_coach_memberships (tenant_id, coach_actor_id, status, academy_id);

CREATE TABLE IF NOT EXISTS kaizo_academy_athletes (
    tenant_id TEXT NOT NULL,
    academy_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    owner_coach_actor_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'LEFT')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    PRIMARY KEY (tenant_id, academy_id, athlete_id),
    FOREIGN KEY (tenant_id, academy_id)
        REFERENCES kaizo_tenant_academies (tenant_id, academy_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, owner_coach_actor_id, athlete_id)
        REFERENCES kaizo_coach_athlete_ownership (tenant_id, coach_actor_id, athlete_id)
        ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_academy_athlete_scope
    ON kaizo_academy_athletes (tenant_id, academy_id, status, athlete_id);

CREATE TABLE IF NOT EXISTS kaizo_academy_athlete_coach_assignments (
    tenant_id TEXT NOT NULL,
    academy_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    coach_actor_id TEXT NOT NULL,
    membership_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'SUSPENDED', 'REVOKED')),
    assigned_at TEXT NOT NULL,
    assigned_by TEXT NOT NULL,
    PRIMARY KEY (tenant_id, academy_id, athlete_id, coach_actor_id),
    FOREIGN KEY (tenant_id, academy_id, athlete_id)
        REFERENCES kaizo_academy_athletes (tenant_id, academy_id, athlete_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, academy_id, coach_actor_id, membership_id)
        REFERENCES kaizo_academy_coach_memberships
                   (tenant_id, academy_id, coach_actor_id, membership_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_academy_assignment_coach_scope
    ON kaizo_academy_athlete_coach_assignments
       (tenant_id, academy_id, coach_actor_id, status, athlete_id);
"""


def ensure_schema() -> None:
    """Create additive contract tables; never alters or migrates production data."""
    if not persistence.is_postgres_enabled():
        raise RuntimeError("Academy contract requires PostgreSQL")
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


def bind_academy(*, tenant_id: str, academy_id: str, actor_id: str, now: str) -> None:
    """Bind one existing academy to exactly one tenant; never equate their IDs."""
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM kaizo_academies WHERE academy_id=%s", (academy_id,))
            if cur.fetchone() is None:
                raise AcademyContractConflict("academy does not exist")
            cur.execute(
                """INSERT INTO kaizo_tenant_academies
                   (academy_id, tenant_id, status, created_at, created_by)
                   VALUES (%s,%s,'ACTIVE',%s,%s)
                   ON CONFLICT (academy_id) DO NOTHING""",
                (academy_id, tenant_id, now, actor_id),
            )
            cur.execute(
                "SELECT tenant_id FROM kaizo_tenant_academies WHERE academy_id=%s FOR UPDATE",
                (academy_id,),
            )
            row = cur.fetchone()
            if row is None or row[0] != tenant_id:
                raise AcademyContractConflict("academy is already bound to another tenant")


def add_coach_membership(
    *, tenant_id: str, academy_id: str, coach_actor_id: str,
    role: str, actor_id: str, now: str,
) -> str:
    allowed = {"OWNER", "ADMIN", "HEAD_COACH", "COACH", "ASSISTANT"}
    if role not in allowed:
        raise AcademyContractConflict("invalid academy coach role")
    membership_id = str(uuid4())
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_academy_coach_memberships
                   (membership_id,tenant_id,academy_id,coach_actor_id,role,status,created_at,created_by)
                   VALUES (%s,%s,%s,%s,%s,'ACTIVE',%s,%s)""",
                (membership_id, tenant_id, academy_id, coach_actor_id, role, now, actor_id),
            )
    return membership_id


def enroll_athlete(
    *, tenant_id: str, academy_id: str, athlete_id: str, owner_coach_actor_id: str,
    actor_id: str, now: str,
) -> None:
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_academy_athletes
                   (tenant_id,academy_id,athlete_id,owner_coach_actor_id,status,created_at,created_by)
                   VALUES (%s,%s,%s,%s,'ACTIVE',%s,%s)""",
                (tenant_id, academy_id, athlete_id, owner_coach_actor_id, now, actor_id),
            )


def assign_coach(
    *, tenant_id: str, academy_id: str, athlete_id: str,
    coach_actor_id: str, actor_id: str, now: str,
) -> None:
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT membership_id FROM kaizo_academy_coach_memberships
                   WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s
                     AND status='ACTIVE' FOR UPDATE""",
                (tenant_id, academy_id, coach_actor_id),
            )
            row = cur.fetchone()
            if row is None:
                raise AcademyContractConflict("active Coach membership is required")
            cur.execute(
                """SELECT 1 FROM kaizo_academy_athletes
                   WHERE tenant_id=%s AND academy_id=%s AND athlete_id=%s AND status='ACTIVE'
                   FOR UPDATE""",
                (tenant_id, academy_id, athlete_id),
            )
            if cur.fetchone() is None:
                raise AcademyContractConflict("active athlete enrolment is required")
            cur.execute(
                """INSERT INTO kaizo_academy_athlete_coach_assignments
                   (tenant_id,academy_id,athlete_id,coach_actor_id,membership_id,
                    status,assigned_at,assigned_by)
                   VALUES (%s,%s,%s,%s,%s,'ACTIVE',%s,%s)""",
                (tenant_id, academy_id, athlete_id, coach_actor_id, row[0], now, actor_id),
            )


def coach_can_access_athlete(*, tenant_id: str, academy_id: str,
                             coach_actor_id: str, athlete_id: str) -> bool:
    """Academy assignment check; must be combined with verified Product API Principal."""
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT EXISTS (
                     SELECT 1
                     FROM kaizo_tenant_academies ta
                     JOIN kaizo_academy_coach_memberships m
                       ON m.tenant_id=ta.tenant_id AND m.academy_id=ta.academy_id
                     JOIN kaizo_academy_athletes aa
                       ON aa.tenant_id=ta.tenant_id AND aa.academy_id=ta.academy_id
                     JOIN kaizo_academy_athlete_coach_assignments a
                       ON a.tenant_id=aa.tenant_id AND a.academy_id=aa.academy_id
                      AND a.athlete_id=aa.athlete_id AND a.coach_actor_id=m.coach_actor_id
                     WHERE ta.tenant_id=%s AND ta.academy_id=%s
                       AND m.coach_actor_id=%s AND aa.athlete_id=%s
                       AND ta.status='ACTIVE' AND m.status='ACTIVE'
                       AND aa.status='ACTIVE' AND a.status='ACTIVE'
                   )""",
                (tenant_id, academy_id, coach_actor_id, athlete_id),
            )
            return bool(cur.fetchone()[0])


def _require_verified_principal(principal: Any, tenant_id: str) -> None:
    """Reject development/header identities; tenant and actor come from verified JWT claims."""
    if (
        principal is None
        or getattr(principal, "verified", False) is not True
        or getattr(principal, "source", None) != "oidc_jwt"
        or not getattr(principal, "actor_id", None)
        or getattr(principal, "tenant_id", None) != tenant_id
        or getattr(principal, "role", None) not in {"academy", "coach"}
    ):
        raise AcademyContractConflict("verified Academy/Coach OIDC principal with matching tenant is required")


def _membership_role(*, tenant_id: str, academy_id: str, coach_actor_id: str) -> str | None:
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT role FROM kaizo_academy_coach_memberships
                   WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s
                     AND status='ACTIVE'""",
                (tenant_id, academy_id, coach_actor_id),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None


def _require_academy_manager(principal: Any, tenant_id: str, academy_id: str) -> None:
    _require_verified_principal(principal, tenant_id)
    if principal.role == "academy":
        return
    role = _membership_role(
        tenant_id=tenant_id, academy_id=academy_id, coach_actor_id=principal.actor_id
    )
    if role not in {"OWNER", "ADMIN", "HEAD_COACH"}:
        raise AcademyContractConflict("active Academy manager membership is required")


def _append_principal_audit(
    *, principal: Any, tenant_id: str, action: str,
    old_value: Any, new_value: Any, now: str,
) -> None:
    # Called inside atomic_transaction: persistence.connection() joins the outer
    # transaction, so an audit failure rolls back the relationship write.
    persistence.append_tenant_audit(
        tenant_id=tenant_id, timestamp=now, who=principal.actor_id,
        action=action, old_value=old_value, new_value=new_value,
        why="Authorized by verified OIDC Principal and Academy membership policy",
    )


def bind_academy_for_principal(*, principal: Any, academy_id: str, now: str) -> None:
    _require_verified_principal(principal, principal.tenant_id if principal else "")
    if principal.role != "academy":
        raise AcademyContractConflict("Academy OIDC role is required to bind a tenant")
    with persistence.atomic_transaction():
        bind_academy(
            tenant_id=principal.tenant_id, academy_id=academy_id,
            actor_id=principal.actor_id, now=now,
        )
        _append_principal_audit(
            principal=principal, tenant_id=principal.tenant_id,
            action="ACADEMY_TENANT_BOUND", old_value=None,
            new_value={"academy_id": academy_id}, now=now,
        )


def add_coach_membership_for_principal(
    *, principal: Any, academy_id: str, coach_actor_id: str,
    role: str, now: str,
) -> str:
    _require_academy_manager(principal, principal.tenant_id, academy_id)
    if principal.role != "academy":
        actor_membership_role = _membership_role(
            tenant_id=principal.tenant_id, academy_id=academy_id,
            coach_actor_id=principal.actor_id,
        )
        permitted_roles = {
            "OWNER": {"ADMIN", "HEAD_COACH", "COACH", "ASSISTANT"},
            "ADMIN": {"HEAD_COACH", "COACH", "ASSISTANT"},
            "HEAD_COACH": {"COACH", "ASSISTANT"},
        }
        if role not in permitted_roles.get(actor_membership_role, set()):
            raise AcademyContractConflict(
                "membership role exceeds the authenticated Coach's delegation authority"
            )
    with persistence.atomic_transaction():
        membership_id = add_coach_membership(
            tenant_id=principal.tenant_id, academy_id=academy_id,
            coach_actor_id=coach_actor_id, role=role,
            actor_id=principal.actor_id, now=now,
        )
        _append_principal_audit(
            principal=principal, tenant_id=principal.tenant_id,
            action="ACADEMY_COACH_MEMBERSHIP_CREATED", old_value=None,
            new_value={"academy_id": academy_id, "coach_actor_id": coach_actor_id,
                       "membership_id": membership_id, "role": role}, now=now,
        )
        return membership_id


def enroll_athlete_for_principal(
    *, principal: Any, academy_id: str, athlete_id: str, now: str,
) -> None:
    _require_academy_manager(principal, principal.tenant_id, academy_id)
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT coach_actor_id FROM kaizo_coach_athlete_ownership
                   WHERE tenant_id=%s AND athlete_id=%s""",
                (principal.tenant_id, athlete_id),
            )
            owners = [str(row[0]) for row in cur.fetchall()]
        if len(owners) != 1:
            raise AcademyContractConflict(
                "athlete must have exactly one unambiguous primary Coach ownership row in this tenant"
            )
        enroll_athlete(
            tenant_id=principal.tenant_id, academy_id=academy_id,
            athlete_id=athlete_id, owner_coach_actor_id=owners[0],
            actor_id=principal.actor_id, now=now,
        )
        _append_principal_audit(
            principal=principal, tenant_id=principal.tenant_id,
            action="ACADEMY_ATHLETE_ENROLLED", old_value=None,
            new_value={"academy_id": academy_id, "athlete_id": athlete_id,
                       "primary_owner_coach_actor_id": owners[0]}, now=now,
        )


def assign_coach_for_principal(
    *, principal: Any, academy_id: str, athlete_id: str,
    coach_actor_id: str, now: str,
) -> None:
    _require_academy_manager(principal, principal.tenant_id, academy_id)
    with persistence.atomic_transaction():
        assign_coach(
            tenant_id=principal.tenant_id, academy_id=academy_id,
            athlete_id=athlete_id, coach_actor_id=coach_actor_id,
            actor_id=principal.actor_id, now=now,
        )
        _append_principal_audit(
            principal=principal, tenant_id=principal.tenant_id,
            action="ACADEMY_ATHLETE_COACH_ASSIGNED", old_value=None,
            new_value={"academy_id": academy_id, "athlete_id": athlete_id,
                       "coach_actor_id": coach_actor_id}, now=now,
        )


def principal_can_access_athlete(
    *, principal: Any, academy_id: str, athlete_id: str,
) -> bool:
    """Verified Coach-only authorization for academy-scoped Product API reads/writes."""
    if principal is None or getattr(principal, "role", None) != "coach":
        return False
    if (
        getattr(principal, "verified", False) is not True
        or getattr(principal, "source", None) != "oidc_jwt"
        or not getattr(principal, "actor_id", None)
        or not getattr(principal, "tenant_id", None)
    ):
        return False
    return coach_can_access_athlete(
        tenant_id=principal.tenant_id, academy_id=academy_id,
        coach_actor_id=principal.actor_id, athlete_id=athlete_id,
    )


def set_membership_status_for_principal(
    *, principal: Any, academy_id: str, coach_actor_id: str,
    status: str, now: str,
) -> None:
    if status not in {"ACTIVE", "SUSPENDED", "REVOKED"}:
        raise AcademyContractConflict("invalid membership status")
    _require_academy_manager(principal, principal.tenant_id, academy_id)
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT status FROM kaizo_academy_coach_memberships
                   WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s
                   FOR UPDATE""",
                (principal.tenant_id, academy_id, coach_actor_id),
            )
            row = cur.fetchone()
            if row is None:
                raise AcademyContractConflict("Coach membership not found")
            old_status = str(row[0])
            cur.execute(
                """SELECT role FROM kaizo_academy_coach_memberships
                   WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s""",
                (principal.tenant_id, academy_id, coach_actor_id),
            )
            target_role_row = cur.fetchone()
            target_role = str(target_role_row[0]) if target_role_row else ""
            if principal.role != "academy":
                actor_role = _membership_role(
                    tenant_id=principal.tenant_id, academy_id=academy_id,
                    coach_actor_id=principal.actor_id,
                )
                if target_role == "OWNER" or actor_role == "HEAD_COACH" and target_role not in {"COACH", "ASSISTANT"}:
                    raise AcademyContractConflict(
                        "Coach membership role is outside the authenticated actor's management scope"
                    )
            cur.execute(
                """UPDATE kaizo_academy_coach_memberships SET status=%s
                   WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s""",
                (status, principal.tenant_id, academy_id, coach_actor_id),
            )
        _append_principal_audit(
            principal=principal, tenant_id=principal.tenant_id,
            action="ACADEMY_COACH_MEMBERSHIP_STATUS_CHANGED",
            old_value={"academy_id": academy_id, "coach_actor_id": coach_actor_id,
                       "status": old_status},
            new_value={"academy_id": academy_id, "coach_actor_id": coach_actor_id,
                       "status": status}, now=now,
        )
