"""PostgreSQL integration tests for Academy/Tenant/Coach membership isolation.

Uses unique fixture identifiers and cleans up only rows created by each test.
Requires KAIZO_PERSISTENCE_MODE=postgres and DATABASE_URL.
"""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

os.environ["KAIZO_PERSISTENCE_MODE"] = "postgres"

import persistence
import academy_ops_runtime
import academy_tenant_contract as contract


pytestmark = pytest.mark.skipif(
    not persistence.is_postgres_enabled(),
    reason="requires disposable PostgreSQL",
)


def _id(prefix):
    return f"{prefix}-{uuid4().hex}"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _fixture():
    persistence.initialize()
    academy_ops_runtime._ensure_schema()
    contract.ensure_schema()
    tenant_a, tenant_b = _id("TENANT"), _id("TENANT")
    academy_a, academy_b = _id("ACADEMY"), _id("ACADEMY")
    coach_a, coach_b, coach_c = _id("COACH"), _id("COACH"), _id("COACH")
    athlete = _id("ATHLETE")
    now = _now()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_academies
                   (academy_id,name,status,owner_id,created_at,updated_at)
                   VALUES (%s,%s,'ACTIVE',%s,%s,%s),(%s,%s,'ACTIVE',%s,%s,%s)""",
                (academy_a, academy_a, coach_a, now, now,
                 academy_b, academy_b, coach_b, now, now),
            )
            cur.execute(
                """INSERT INTO kaizo_athletes
                   (athlete_id,display_name,status,metadata,created_at,updated_at)
                   VALUES (%s,'Contract test athlete','ACTIVE','{}'::jsonb,%s,%s)""",
                (athlete, now, now),
            )
            cur.execute(
                """INSERT INTO kaizo_coach_athlete_ownership
                   (athlete_id,tenant_id,coach_actor_id,assigned_at)
                   VALUES (%s,%s,%s,%s)""",
                (athlete, tenant_a, coach_a, now),
            )
        conn.commit()
    contract.bind_academy(tenant_id=tenant_a, academy_id=academy_a, actor_id=coach_a, now=now)
    contract.bind_academy(tenant_id=tenant_a, academy_id=academy_b, actor_id=coach_a, now=now)
    contract.add_coach_membership(tenant_id=tenant_a, academy_id=academy_a,
                                  coach_actor_id=coach_a, role="HEAD_COACH", actor_id=coach_a, now=now)
    contract.add_coach_membership(tenant_id=tenant_a, academy_id=academy_a,
                                  coach_actor_id=coach_b, role="COACH", actor_id=coach_a, now=now)
    contract.add_coach_membership(tenant_id=tenant_a, academy_id=academy_b,
                                  coach_actor_id=coach_c, role="COACH", actor_id=coach_a, now=now)
    contract.enroll_athlete(tenant_id=tenant_a, academy_id=academy_a,
                            athlete_id=athlete, actor_id=coach_a, now=now)
    contract.assign_coach(tenant_id=tenant_a, academy_id=academy_a, athlete_id=athlete,
                          coach_actor_id=coach_a, actor_id=coach_a, now=now)
    return tenant_a, tenant_b, academy_a, academy_b, coach_a, coach_b, coach_c, athlete


def _cleanup(f):
    tenant_a, tenant_b, academy_a, academy_b, coach_a, coach_b, coach_c, athlete = f
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kaizo_academy_athlete_coach_assignments WHERE tenant_id=%s AND academy_id IN (%s,%s)",
                        (tenant_a, academy_a, academy_b))
            cur.execute("DELETE FROM kaizo_academy_athletes WHERE tenant_id=%s AND academy_id IN (%s,%s)",
                        (tenant_a, academy_a, academy_b))
            cur.execute("DELETE FROM kaizo_academy_coach_memberships WHERE tenant_id=%s AND academy_id IN (%s,%s)",
                        (tenant_a, academy_a, academy_b))
            cur.execute("DELETE FROM kaizo_tenant_academies WHERE academy_id IN (%s,%s)",
                        (academy_a, academy_b))
            cur.execute("DELETE FROM kaizo_coach_athlete_ownership WHERE athlete_id=%s", (athlete,))
            cur.execute("DELETE FROM kaizo_athletes WHERE athlete_id=%s", (athlete,))
            cur.execute("DELETE FROM kaizo_academies WHERE academy_id IN (%s,%s)", (academy_a, academy_b))
        conn.commit()


def test_cross_coach_and_cross_academy_isolation():
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, academy_b, coach_a, coach_b, coach_c, athlete = f
        assert contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_a, athlete_id=athlete
        )
        assert not contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_b, athlete_id=athlete
        )
        assert not contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_b, coach_actor_id=coach_c, athlete_id=athlete
        )
    finally:
        _cleanup(f)


def test_cross_tenant_and_wrong_academy_are_denied():
    f = _fixture()
    try:
        tenant, other_tenant, academy_a, academy_b, coach_a, _coach_b, _coach_c, athlete = f
        assert not contract.coach_can_access_athlete(
            tenant_id=other_tenant, academy_id=academy_a, coach_actor_id=coach_a, athlete_id=athlete
        )
        assert not contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_b, coach_actor_id=coach_a, athlete_id=athlete
        )
    finally:
        _cleanup(f)


def test_academy_cannot_be_rebound_to_a_different_tenant():
    f = _fixture()
    try:
        tenant, other_tenant, academy_a, _academy_b, coach_a, *_ = f
        with pytest.raises(contract.AcademyContractConflict):
            contract.bind_academy(
                tenant_id=other_tenant, academy_id=academy_a, actor_id=coach_a, now=_now()
            )
    finally:
        _cleanup(f)


def test_assignment_requires_active_membership_and_enrollment():
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, _academy_b, _coach_a, coach_b, coach_c, athlete = f
        # coach_c is a real member, but only in academy_b: cross-academy assignment is denied.
        with pytest.raises(contract.AcademyContractConflict):
            contract.assign_coach(
                tenant_id=tenant, academy_id=academy_a, athlete_id=athlete,
                coach_actor_id=coach_c, actor_id=coach_c, now=_now()
            )
        # coach_b is a member of academy_a, but an athlete must be enrolled before assignment.
        with pytest.raises(contract.AcademyContractConflict):
            contract.assign_coach(
                tenant_id=tenant, academy_id=academy_a, athlete_id=_id("UNKNOWN"),
                coach_actor_id=coach_b, actor_id=coach_b, now=_now()
            )
        assert not contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_b,
            athlete_id=f[-1]
        )
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE kaizo_academy_coach_memberships SET status='SUSPENDED' "
                    "WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s",
                    (tenant, academy_a, coach_b),
                )
            conn.commit()
        assert not contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_b,
            athlete_id=f[-1]
        )
    finally:
        _cleanup(f)
