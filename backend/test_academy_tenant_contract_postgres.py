"""PostgreSQL integration tests for Academy/Tenant/Coach membership isolation.

Uses unique fixture identifiers and cleans up only rows created by each test.
Requires KAIZO_PERSISTENCE_MODE=postgres and DATABASE_URL.
"""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

os.environ.setdefault("KAIZO_PERSISTENCE_MODE", "postgres")

import persistence
import academy_ops_runtime
import academy_tenant_contract as contract
from types import SimpleNamespace


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL") or not persistence.is_postgres_enabled(),
    reason="requires disposable PostgreSQL via DATABASE_URL",
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
                            athlete_id=athlete, owner_coach_actor_id=coach_a,
                            actor_id=coach_a, now=now)
    contract.assign_coach(tenant_id=tenant_a, academy_id=academy_a, athlete_id=athlete,
                          coach_actor_id=coach_a, actor_id=coach_a, now=now)
    return tenant_a, tenant_b, academy_a, academy_b, coach_a, coach_b, coach_c, athlete


def _cleanup(f):
    tenant_a, tenant_b, academy_a, academy_b, coach_a, coach_b, coach_c, athlete = f
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM kaizo_audit_logs WHERE tenant_id IN (%s,%s)", (tenant_a, tenant_b))
            cur.execute("DELETE FROM kaizo_academy_athlete_coach_assignments WHERE academy_id IN (%s,%s)",
                        (academy_a, academy_b))
            cur.execute("DELETE FROM kaizo_academy_athletes WHERE tenant_id=%s AND academy_id IN (%s,%s)",
                        (tenant_a, academy_a, academy_b))
            cur.execute("DELETE FROM kaizo_academy_coach_memberships WHERE academy_id IN (%s,%s)",
                        (academy_a, academy_b))
            cur.execute("DELETE FROM kaizo_tenant_academies WHERE academy_id IN (%s,%s)",
                        (academy_a, academy_b))
            cur.execute("DELETE FROM kaizo_coach_athlete_ownership WHERE athlete_id=%s", (athlete,))
            cur.execute("DELETE FROM kaizo_athletes WHERE athlete_id=%s", (athlete,))
            cur.execute("DELETE FROM kaizo_academies WHERE academy_id IN (%s,%s)", (academy_a, academy_b))
        conn.commit()


def test_cross_coach_and_cross_academy_isolation():
    f = _fixture()
    try:
        tenant, other_tenant, academy_a, academy_b, coach_a, coach_b, coach_c, athlete = f
        assert contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_a, athlete_id=athlete
        )
        assert not contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_b, athlete_id=athlete
        )
        # Coach C is an active member of another Academy in the same Tenant, but the athlete is not enrolled there.
        assert not contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_b, coach_actor_id=coach_c, athlete_id=athlete
        )
    finally:
        _cleanup(f)


def test_cross_tenant_and_wrong_academy_are_denied():
    f = _fixture()
    try:
        tenant, other_tenant, academy_a, academy_b, coach_a, _coach_b, coach_c, athlete = f
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


ALL_ACADEMY_PERMISSIONS = frozenset({
    "academy:read", "academy:tenant:bind", "academy:membership:manage",
    "academy:athlete:enroll", "academy:coach:assign",
})


def _principal(actor_id, tenant_id, role="coach", verified=True, source="oidc_jwt",
               permissions=ALL_ACADEMY_PERMISSIONS, academy_id=None):
    return SimpleNamespace(
        actor_id=actor_id, role=role, tenant_id=tenant_id,
        resource_owner_id=None, verified=verified, source=source,
        permissions=permissions, academy_id=academy_id,
    )


def test_verified_principal_service_enforces_assignment_and_writes_tenant_audit():
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, _academy_b, coach_a, coach_b, _coach_c, athlete = f
        principal = _principal(coach_a, tenant)
        assert contract.principal_can_access_athlete(
            principal=principal, academy_id=academy_a, athlete_id=athlete
        )
        contract.assign_coach_for_principal(
            principal=principal, academy_id=academy_a, athlete_id=athlete,
            coach_actor_id=coach_b, now=_now(),
        )
        assert contract.principal_can_access_athlete(
            principal=_principal(coach_b, tenant), academy_id=academy_a, athlete_id=athlete
        )
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT action, who, tenant_id FROM kaizo_audit_logs "
                    "WHERE tenant_id=%s AND action='ACADEMY_ATHLETE_COACH_ASSIGNED' ORDER BY id DESC LIMIT 1",
                    (tenant,),
                )
                row = cur.fetchone()
        assert row == ("ACADEMY_ATHLETE_COACH_ASSIGNED", coach_a, tenant)
    finally:
        _cleanup(f)


def test_unverified_or_wrong_tenant_principal_cannot_access_athlete():
    f = _fixture()
    try:
        tenant, other_tenant, academy_a, _academy_b, coach_a, _coach_b, _coach_c, athlete = f
        assert not contract.principal_can_access_athlete(
            principal=_principal(coach_a, tenant, verified=False),
            academy_id=academy_a, athlete_id=athlete,
        )
        assert not contract.principal_can_access_athlete(
            principal=_principal(coach_a, other_tenant),
            academy_id=academy_a, athlete_id=athlete,
        )
        assert not contract.principal_can_access_athlete(
            principal=_principal(coach_a, tenant, role="academy"),
            academy_id=academy_a, athlete_id=athlete,
        )
    finally:
        _cleanup(f)


def test_audit_failure_rolls_back_coach_assignment(monkeypatch):
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, _academy_b, coach_a, coach_b, _coach_c, athlete = f
        def fail_audit(**_kwargs):
            raise RuntimeError("simulated durable audit failure")
        monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
        with pytest.raises(RuntimeError, match="audit failure"):
            contract.assign_coach_for_principal(
                principal=_principal(coach_a, tenant), academy_id=academy_a,
                athlete_id=athlete, coach_actor_id=coach_b, now=_now(),
            )
        assert not contract.coach_can_access_athlete(
            tenant_id=tenant, academy_id=academy_a,
            coach_actor_id=coach_b, athlete_id=athlete,
        )
    finally:
        _cleanup(f)


def test_enrollment_rejects_athlete_without_tenant_ownership():
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, _academy_b, coach_a, *_rest = f
        with pytest.raises(contract.AcademyContractConflict, match="exactly one"):
            contract.enroll_athlete_for_principal(
                principal=_principal(coach_a, tenant), academy_id=academy_a,
                athlete_id=_id("UNOWNED"), now=_now(),
            )
    finally:
        _cleanup(f)


def test_head_coach_cannot_escalate_membership_to_admin_or_owner():
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, _academy_b, coach_a, *_rest = f
        principal = _principal(coach_a, tenant)
        for elevated_role in ("OWNER", "ADMIN"):
            with pytest.raises(
                contract.AcademyContractConflict, match="delegation authority"
            ):
                contract.add_coach_membership_for_principal(
                    principal=principal, academy_id=academy_a,
                    coach_actor_id=_id("NEWCOACH"), role=elevated_role, now=_now(),
                )
    finally:
        _cleanup(f)


def test_assigned_roster_query_isolated_by_coach_academy_and_tenant():
    f = _fixture()
    try:
        tenant, other_tenant, academy_a, academy_b, coach_a, coach_b, coach_c, athlete = f
        contract.assign_coach(
            tenant_id=tenant, academy_id=academy_a, athlete_id=athlete,
            coach_actor_id=coach_b, actor_id=coach_a, now=_now(),
        )
        rows_a = contract.list_assigned_athletes_for_coach(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_a,
        )
        rows_b = contract.list_assigned_athletes_for_coach(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_b,
        )
        rows_wrong_academy = contract.list_assigned_athletes_for_coach(
            tenant_id=tenant, academy_id=academy_b, coach_actor_id=coach_c,
        )
        rows_wrong_tenant = contract.list_assigned_athletes_for_coach(
            tenant_id=other_tenant, academy_id=academy_a, coach_actor_id=coach_a,
        )
        assert [row["athlete_id"] for row in rows_a] == [athlete]
        assert [row["athlete_id"] for row in rows_b] == [athlete]
        assert rows_wrong_academy == []
        assert rows_wrong_tenant == []
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE kaizo_academy_coach_memberships SET status='SUSPENDED' "
                    "WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s",
                    (tenant, academy_a, coach_b),
                )
            conn.commit()
        assert contract.list_assigned_athletes_for_coach(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=coach_b,
        ) == []
    finally:
        _cleanup(f)


def test_active_academy_membership_listing_is_tenant_and_coach_scoped():
    f = _fixture()
    try:
        tenant, other_tenant, academy_a, academy_b, coach_a, _coach_b, coach_c, _athlete = f
        assert contract.list_active_academies_for_coach(
            tenant_id=tenant, coach_actor_id=coach_a,
        ) == [{"academy_id": academy_a, "academy_name": academy_a}]
        assert contract.list_active_academies_for_coach(
            tenant_id=tenant, coach_actor_id=coach_c,
        ) == [{"academy_id": academy_b, "academy_name": academy_b}]
        assert contract.list_active_academies_for_coach(
            tenant_id=other_tenant, coach_actor_id=coach_a,
        ) == []
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE kaizo_academy_coach_memberships SET status='REVOKED' "
                    "WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s",
                    (tenant, academy_a, coach_a),
                )
            conn.commit()
        assert contract.list_active_academies_for_coach(
            tenant_id=tenant, coach_actor_id=coach_a,
        ) == []
    finally:
        _cleanup(f)

def test_membership_lifecycle_enforces_full_delegation_hierarchy():
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, _academy_b, head_coach, _coach_b, _coach_c, _athlete = f
        admin_actor, admin_peer = _id("ADMIN"), _id("ADMIN")
        contract.add_coach_membership(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=admin_actor,
            role="ADMIN", actor_id=head_coach, now=_now(),
        )
        contract.add_coach_membership(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=admin_peer,
            role="ADMIN", actor_id=head_coach, now=_now(),
        )

        # HEAD_COACH may manage COACH/ASSISTANT only, not ADMIN.
        with pytest.raises(
            contract.AcademyContractConflict, match="management scope"
        ):
            contract.set_membership_status_for_principal(
                principal=_principal(head_coach, tenant),
                academy_id=academy_a, coach_actor_id=admin_actor,
                status="SUSPENDED", now=_now(),
            )

        # ADMIN may manage HEAD_COACH/COACH/ASSISTANT, not a peer ADMIN.
        with pytest.raises(
            contract.AcademyContractConflict, match="management scope"
        ):
            contract.set_membership_status_for_principal(
                principal=_principal(admin_actor, tenant),
                academy_id=academy_a, coach_actor_id=admin_peer,
                status="REVOKED", now=_now(),
            )

        # A valid lower-level lifecycle action remains available.
        contract.set_membership_status_for_principal(
            principal=_principal(admin_actor, tenant),
            academy_id=academy_a, coach_actor_id=head_coach,
            status="SUSPENDED", now=_now(),
        )
        assert contract._membership_role(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=head_coach
        ) is None
    finally:
        _cleanup(f)

def test_academy_mutations_deny_missing_explicit_oidc_permissions_before_database_access():
    principal = _principal(
        "coach-no-permissions", "tenant-a", permissions=frozenset()
    )
    with pytest.raises(
        contract.AcademyContractConflict, match="academy:membership:manage"
    ):
        contract.add_coach_membership_for_principal(
            principal=principal, academy_id="academy-a",
            coach_actor_id="coach-b", role="COACH", now=_now(),
        )
    with pytest.raises(
        contract.AcademyContractConflict, match="academy:athlete:enroll"
    ):
        contract.enroll_athlete_for_principal(
            principal=principal, academy_id="academy-a",
            athlete_id="athlete-a", now=_now(),
        )
    with pytest.raises(
        contract.AcademyContractConflict, match="academy:coach:assign"
    ):
        contract.assign_coach_for_principal(
            principal=principal, academy_id="academy-a",
            athlete_id="athlete-a", coach_actor_id="coach-b", now=_now(),
        )
    with pytest.raises(
        contract.AcademyContractConflict, match="academy:membership:manage"
    ):
        contract.set_membership_status_for_principal(
            principal=principal, academy_id="academy-a",
            coach_actor_id="coach-b", status="REVOKED", now=_now(),
        )


def test_academy_tenant_binding_requires_explicit_oidc_permission():
    principal = _principal(
        "academy-admin", "tenant-a", role="academy", permissions=frozenset()
    )
    with pytest.raises(
        contract.AcademyContractConflict, match="academy:tenant:bind"
    ):
        contract.bind_academy_for_principal(
            principal=principal, academy_id="academy-a", now=_now()
        )


def test_academy_principal_is_confined_to_its_signed_academy_claim():
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, academy_b, coach_a, *_rest = f
        principal = _principal(coach_a, tenant, role="academy", academy_id=academy_a)
        new_coach = _id("NEWCOACH")
        contract.add_coach_membership_for_principal(
            principal=principal, academy_id=academy_a,
            coach_actor_id=new_coach, role="COACH", now=_now(),
        )
        with pytest.raises(contract.AcademyContractConflict, match="signed academy_id"):
            contract.add_coach_membership_for_principal(
                principal=principal, academy_id=academy_b,
                coach_actor_id=_id("CROSSACADEMY"), role="COACH", now=_now(),
            )
        with pytest.raises(contract.AcademyContractConflict, match="signed academy_id"):
            contract.add_coach_membership_for_principal(
                principal=_principal(coach_a, tenant, role="academy"),
                academy_id=academy_a, coach_actor_id=_id("NOCLAIM"),
                role="COACH", now=_now(),
            )
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT academy_id FROM kaizo_academy_coach_memberships "
                    "WHERE tenant_id=%s AND coach_actor_id=%s",
                    (tenant, new_coach),
                )
                rows = cur.fetchall()
        assert rows == [(academy_a,)]
    finally:
        _cleanup(f)


def test_membership_status_changes_obey_the_same_delegation_hierarchy():
    f = _fixture()
    try:
        tenant, _other_tenant, academy_a, _academy_b, coach_a, coach_b, _coach_c, _athlete = f
        admin_a, admin_b, owner = _id("ADMIN"), _id("ADMIN"), _id("OWNER")
        contract.add_coach_membership(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=admin_a,
            role="ADMIN", actor_id=coach_a, now=_now(),
        )
        contract.add_coach_membership(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=admin_b,
            role="ADMIN", actor_id=coach_a, now=_now(),
        )
        contract.add_coach_membership(
            tenant_id=tenant, academy_id=academy_a, coach_actor_id=owner,
            role="OWNER", actor_id=coach_a, now=_now(),
        )
        with pytest.raises(contract.AcademyContractConflict, match="management scope"):
            contract.set_membership_status_for_principal(
                principal=_principal(admin_a, tenant), academy_id=academy_a,
                coach_actor_id=owner, status="REVOKED", now=_now(),
            )
        with pytest.raises(contract.AcademyContractConflict, match="management scope"):
            contract.set_membership_status_for_principal(
                principal=_principal(admin_a, tenant), academy_id=academy_a,
                coach_actor_id=admin_b, status="REVOKED", now=_now(),
            )
        with pytest.raises(contract.AcademyContractConflict, match="management scope"):
            contract.set_membership_status_for_principal(
                principal=_principal(coach_a, tenant), academy_id=academy_a,
                coach_actor_id=admin_a, status="REVOKED", now=_now(),
            )
        contract.set_membership_status_for_principal(
            principal=_principal(coach_a, tenant), academy_id=academy_a,
            coach_actor_id=coach_b, status="SUSPENDED", now=_now(),
        )
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM kaizo_academy_coach_memberships "
                    "WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s",
                    (tenant, academy_a, coach_b),
                )
                assert cur.fetchone() == ("SUSPENDED",)
    finally:
        _cleanup(f)


def test_all_principal_mutations_roll_back_when_tenant_audit_fails(monkeypatch):
    f = _fixture()
    tenant, _other_tenant, academy_a, _academy_b, coach_a, coach_b, _coach_c, athlete = f
    new_coach, new_athlete, new_academy = _id("NEWCOACH"), _id("ATHLETE"), _id("ACADEMY")
    now = _now()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_academies
                   (academy_id,name,status,owner_id,created_at,updated_at)
                   VALUES (%s,%s,'ACTIVE',%s,%s,%s)""",
                (new_academy, new_academy, coach_a, now, now),
            )
            cur.execute(
                """INSERT INTO kaizo_athletes
                   (athlete_id,display_name,status,metadata,created_at,updated_at)
                   VALUES (%s,'Rollback athlete','ACTIVE','{}'::jsonb,%s,%s)""",
                (new_athlete, now, now),
            )
            cur.execute(
                """INSERT INTO kaizo_coach_athlete_ownership
                   (athlete_id,tenant_id,coach_actor_id,assigned_at)
                   VALUES (%s,%s,%s,%s)""",
                (new_athlete, tenant, coach_a, now),
            )
        conn.commit()

    def fail_audit(**_kwargs):
        raise RuntimeError("simulated durable audit failure")

    monkeypatch.setattr(persistence, "append_tenant_audit", fail_audit)
    academy_principal = _principal(coach_a, tenant, role="academy", academy_id=academy_a)
    new_academy_principal = _principal(coach_a, tenant, role="academy", academy_id=new_academy)

    try:
        with pytest.raises(RuntimeError, match="audit failure"):
            contract.bind_academy_for_principal(
                principal=new_academy_principal, academy_id=new_academy, now=now,
            )
        with pytest.raises(RuntimeError, match="audit failure"):
            contract.add_coach_membership_for_principal(
                principal=academy_principal, academy_id=academy_a,
                coach_actor_id=new_coach, role="COACH", now=now,
            )
        with pytest.raises(RuntimeError, match="audit failure"):
            contract.enroll_athlete_for_principal(
                principal=academy_principal, academy_id=academy_a,
                athlete_id=new_athlete, now=now,
            )
        with pytest.raises(RuntimeError, match="audit failure"):
            contract.assign_coach_for_principal(
                principal=academy_principal, academy_id=academy_a,
                athlete_id=athlete, coach_actor_id=coach_b, now=now,
            )
        with pytest.raises(RuntimeError, match="audit failure"):
            contract.set_membership_status_for_principal(
                principal=academy_principal, academy_id=academy_a,
                coach_actor_id=coach_b, status="SUSPENDED", now=now,
            )

        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM kaizo_tenant_academies WHERE academy_id=%s",
                    (new_academy,),
                )
                assert cur.fetchone() is None
                cur.execute(
                    "SELECT 1 FROM kaizo_academy_coach_memberships "
                    "WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s",
                    (tenant, academy_a, new_coach),
                )
                assert cur.fetchone() is None
                cur.execute(
                    "SELECT 1 FROM kaizo_academy_athletes "
                    "WHERE tenant_id=%s AND academy_id=%s AND athlete_id=%s",
                    (tenant, academy_a, new_athlete),
                )
                assert cur.fetchone() is None
                cur.execute(
                    "SELECT 1 FROM kaizo_academy_athlete_coach_assignments "
                    "WHERE tenant_id=%s AND academy_id=%s AND athlete_id=%s AND coach_actor_id=%s",
                    (tenant, academy_a, athlete, coach_b),
                )
                assert cur.fetchone() is None
                cur.execute(
                    "SELECT status FROM kaizo_academy_coach_memberships "
                    "WHERE tenant_id=%s AND academy_id=%s AND coach_actor_id=%s",
                    (tenant, academy_a, coach_b),
                )
                assert cur.fetchone() == ("ACTIVE",)
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM kaizo_academy_athletes WHERE athlete_id=%s", (new_athlete,))
                cur.execute("DELETE FROM kaizo_coach_athlete_ownership WHERE athlete_id=%s", (new_athlete,))
                cur.execute("DELETE FROM kaizo_athletes WHERE athlete_id=%s", (new_athlete,))
                cur.execute("DELETE FROM kaizo_tenant_academies WHERE academy_id=%s", (new_academy,))
                cur.execute("DELETE FROM kaizo_academies WHERE academy_id=%s", (new_academy,))
            conn.commit()
        _cleanup(f)

