"""Ephemeral-PostgreSQL acceptance tests for durable Phase 4 stores."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import uuid

import persistence
import phase4_identity_store as store



def _test_atomic_core_resource_binding():
    """Resource rows and ownership bindings commit or roll back together."""
    athlete_id = "atomic-athlete-" + uuid.uuid4().hex
    tenant_id = "atomic-academy"
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kaizo_tenants (tenant_id, display_name, status) "
                "VALUES (%s, %s, 'active') ON CONFLICT (tenant_id) DO NOTHING",
                (tenant_id, "Atomic test academy"),
            )
            cur.execute(
                "INSERT INTO kaizo_tenants (tenant_id, display_name, status) "
                "VALUES ('different-academy', 'Different academy', 'active') "
                "ON CONFLICT (tenant_id) DO NOTHING"
            )
        conn.commit()
    athlete = {
        "athlete_id": athlete_id, "display_name": "Atomic test athlete",
        "status": "ACTIVE", "metadata": {}, "created_at": "2026-10-13T00:00:00",
        "updated_at": "2026-10-13T00:00:00",
    }
    persistence.persist_core_resource_and_binding(
        resource_type="athlete", resource=athlete, tenant_id=tenant_id,
        bound_by_actor_id="atomic-test-coach", correlation_id="atomic-athlete-create",
    )
    assert store.get_resource_tenant(resource_type="athlete", resource_id=athlete_id) == tenant_id
    assert persistence.get_athlete(athlete_id)["display_name"] == "Atomic test athlete"
    assert any(
        row["resource_id"] == athlete_id and row["decision"] == "allow"
        for row in store.list_authorization_audit(correlation_id="atomic-athlete-create")
    )

    assessment_id = "atomic-assessment-" + uuid.uuid4().hex
    assessment = {
        "assessment_id": assessment_id, "athlete_id": athlete_id,
        "template_id": "ATOMIC-TPL", "measurements": {"score": 1},
        "recorded_by": "atomic-test-coach", "assessed_at": "2026-10-13T00:00:00",
        "created_at": "2026-10-13T00:00:00",
    }
    persistence.persist_core_resource_and_binding(
        resource_type="assessment", resource=assessment, tenant_id=tenant_id,
        bound_by_actor_id="atomic-test-coach", correlation_id="atomic-assessment-create",
    )
    assert store.get_resource_tenant(resource_type="assessment", resource_id=assessment_id) == tenant_id
    assert persistence.get_assessment(assessment_id)["athlete_id"] == athlete_id

    conflicting_id = "atomic-conflict-" + uuid.uuid4().hex
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO kaizo_resource_tenant_bindings
                   (resource_type, resource_id, tenant_id, bound_by_actor_id)
                   VALUES ('athlete', %s, 'different-academy', 'seed')""",
                (conflicting_id,),
            )
        conn.commit()
    conflicting = dict(athlete, athlete_id=conflicting_id, display_name="Must rollback")
    try:
        persistence.persist_core_resource_and_binding(
            resource_type="athlete", resource=conflicting, tenant_id=tenant_id,
            bound_by_actor_id="atomic-test-coach", correlation_id="atomic-conflict-rollback",
        )
    except persistence.PersistenceConfigurationError:
        pass
    else:
        raise AssertionError("Conflicting ownership must fail closed")
    assert persistence.get_athlete(conflicting_id) is None
    assert store.get_resource_tenant(resource_type="athlete", resource_id=conflicting_id) == "different-academy"
    assert store.list_authorization_audit(correlation_id="atomic-conflict-rollback") == []

    mismatched_assessment_id = "atomic-assessment-conflict-" + uuid.uuid4().hex
    mismatched_assessment = {
        "assessment_id": mismatched_assessment_id, "athlete_id": conflicting_id,
        "template_id": "ATOMIC-TPL", "measurements": {"score": 1},
        "recorded_by": "atomic-test-coach", "assessed_at": "2026-10-13T00:00:00",
        "created_at": "2026-10-13T00:00:00",
    }
    try:
        persistence.persist_core_resource_and_binding(
            resource_type="assessment", resource=mismatched_assessment,
            tenant_id=tenant_id, bound_by_actor_id="atomic-test-coach",
        )
    except persistence.PersistenceConfigurationError:
        pass
    else:
        raise AssertionError("Assessment cannot cross the parent athlete tenant")
    assert persistence.get_assessment(mismatched_assessment_id) is None

def main():
    assert persistence.is_postgres_enabled()
    migration = Path("migrations/0001_phase4_identity_consent.sql").read_text()
    canonical_migration = Path("migrations/20261012_phase4_identity_consent_canonical.sql").read_text()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(migration)
        conn.commit()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(canonical_migration)
        conn.commit()

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kaizo_tenants (tenant_id, display_name, status) "
                "VALUES ('test-academy', 'Phase 4 test academy', 'active') "
                "ON CONFLICT (tenant_id) DO NOTHING"
            )
            cur.execute(
                "INSERT INTO kaizo_tenants (tenant_id, display_name, status) "
                "VALUES ('academy-a', 'Phase 4 route-test academy', 'active') "
                "ON CONFLICT (tenant_id) DO NOTHING"
            )
        conn.commit()

    _test_atomic_core_resource_binding()

    # Clean only the four dedicated Phase 4 test tables in this ephemeral DB.
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE kaizo_authorization_audit, kaizo_child_consents, "
                "kaizo_guardian_relationships, kaizo_tenant_memberships"
            )
        conn.commit()

    store.record_membership(
        membership_id="test-member-v1", actor_id="test-coach",
        academy_id="test-academy", role="coach", status="active", version=1,
    )
    assert store.has_active_membership(
        actor_id="test-coach", academy_id="test-academy", role="coach"
    )
    assert not store.has_active_membership(
        actor_id="test-coach", academy_id="other-academy", role="coach"
    )
    store.record_membership(
        membership_id="test-member-v2", actor_id="test-coach",
        academy_id="test-academy", role="coach", status="revoked", version=2,
    )
    assert not store.has_active_membership(
        actor_id="test-coach", academy_id="test-academy", role="coach"
    )

    now = datetime.now(timezone.utc)
    store.record_guardian_relationship(
        relationship_id="test-guardian-v1", child_id="test-child",
        guardian_actor_id="test-guardian", academy_id="test-academy",
        verification_status="verified", version=1,
        verified_by="trusted-test-admin", verified_at=now,
    )
    assert store.has_verified_guardian_relationship(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy",
    )
    assert not store.has_verified_guardian_relationship(
        child_id="test-child", guardian_actor_id="different-guardian",
        academy_id="test-academy",
    )
    # Consent is valid only while the latest guardian relationship is verified.
    store.record_child_consent(
        consent_id="test-consent-v1", child_id="test-child",
        guardian_actor_id="test-guardian", academy_id="test-academy",
        resource="training_plan", action="read", state="active",
        expires_at=now + timedelta(days=1), recorded_by_actor_id="test-guardian",
        version=1,
    )
    assert store.has_active_child_consent(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy", resource="training_plan", action="read",
    )
    assert not store.has_active_child_consent(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy", resource="training_plan", action="write",
    )
    store.record_child_consent(
        consent_id="test-consent-v2", child_id="test-child",
        guardian_actor_id="test-guardian", academy_id="test-academy",
        resource="training_plan", action="read", state="revoked",
        expires_at=now + timedelta(days=1), recorded_by_actor_id="test-guardian",
        version=2,
    )
    assert not store.has_active_child_consent(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy", resource="training_plan", action="read",
    )
    store.record_child_consent(
        consent_id="test-consent-expired", child_id="test-child",
        guardian_actor_id="test-guardian", academy_id="test-academy",
        resource="assessment", action="read", state="active",
        expires_at=now - timedelta(seconds=1), recorded_by_actor_id="test-guardian",
        version=1,
    )
    assert not store.has_active_child_consent(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy", resource="assessment", action="read",
    )

    # An active consent must stop working after relationship revocation.
    store.record_child_consent(
        consent_id="test-consent-relationship-check", child_id="test-child",
        guardian_actor_id="test-guardian", academy_id="test-academy",
        resource="training_session", action="read", state="active",
        expires_at=now + timedelta(days=1), recorded_by_actor_id="test-guardian",
        version=1,
    )
    assert store.has_active_child_consent(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy", resource="training_session", action="read",
    )
    store.record_guardian_relationship(
        relationship_id="test-guardian-v2", child_id="test-child",
        guardian_actor_id="test-guardian", academy_id="test-academy",
        verification_status="revoked", version=2,
    )
    assert not store.has_verified_guardian_relationship(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy",
    )
    assert not store.has_active_child_consent(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy", resource="training_session", action="read",
    )

    store.append_authorization_audit(
        event_id="test-authz-deny-1", correlation_id="test-correlation-1",
        actor_id="test-coach", actor_role="coach", academy_id="test-academy",
        resource_type="training_plan", resource_id="test-plan", action="read",
        decision="deny", reason_code="CONSENT_REVOKED", consent_id="test-consent-v2",
        policy_version="test-policy-v1", request_route="/test/training-plans/test-plan",
    )
    audit = store.list_authorization_audit(correlation_id="test-correlation-1")
    assert len(audit) == 1
    assert audit[0]["decision"] == "deny"
    assert audit[0]["reason_code"] == "CONSENT_REVOKED"

    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE kaizo_authorization_audit, kaizo_child_consents, "
                "kaizo_guardian_relationships, kaizo_tenant_memberships"
            )
        conn.commit()
    print("PHASE 4 IDENTITY/CONSENT EPHEMERAL POSTGRES ACCEPTANCE PASS")


if __name__ == "__main__":
    main()
