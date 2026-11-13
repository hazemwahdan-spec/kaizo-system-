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
CREATE UNIQUE INDEX IF NOT EXISTS uq_coach_ownership_tenant_athlete
    ON kaizo_coach_athlete_ownership (tenant_id, athlete_id);

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
    FOREIGN KEY (tenant_id, academy_id)
        REFERENCES kaizo_tenant_academies (tenant_id, academy_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS idx_academy_membership_actor_scope
    ON kaizo_academy_coach_memberships (tenant_id, coach_actor_id, status, academy_id);

CREATE TABLE IF NOT EXISTS kaizo_academy_athletes (
    tenant_id TEXT NOT NULL,
    academy_id TEXT NOT NULL,
    athlete_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'INACTIVE', 'LEFT')),
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL,
    PRIMARY KEY (tenant_id, academy_id, athlete_id),
    FOREIGN KEY (tenant_id, academy_id)
        REFERENCES kaizo_tenant_academies (tenant_id, academy_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, athlete_id)
        REFERENCES kaizo_coach_athlete_ownership (tenant_id, athlete_id) ON DELETE RESTRICT
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
    FOREIGN KEY (tenant_id, academy_id, coach_actor_id)
        REFERENCES kaizo_academy_coach_memberships (tenant_id, academy_id, coach_actor_id) ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, academy_id, membership_id)
        REFERENCES kaizo_academy_coach_memberships (tenant_id, academy_id, membership_id) ON DELETE RESTRICT
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
    *, tenant_id: str, academy_id: str, athlete_id: str, actor_id: str, now: str,
) -> None:
    with persistence.atomic_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_academy_athletes
                   (tenant_id,academy_id,athlete_id,status,created_at,created_by)
                   VALUES (%s,%s,%s,'ACTIVE',%s,%s)""",
                (tenant_id, academy_id, athlete_id, now, actor_id),
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
