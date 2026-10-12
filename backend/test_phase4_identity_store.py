"""Ephemeral-PostgreSQL acceptance tests for durable Phase 4 stores."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import persistence
import phase4_identity_store as store


def main():
    assert persistence.is_postgres_enabled()
    migration = Path("migrations/0001_phase4_identity_consent.sql").read_text()
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(migration)
        conn.commit()

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
    store.record_guardian_relationship(
        relationship_id="test-guardian-v2", child_id="test-child",
        guardian_actor_id="test-guardian", academy_id="test-academy",
        verification_status="revoked", version=2,
    )
    assert not store.has_verified_guardian_relationship(
        child_id="test-child", guardian_actor_id="test-guardian",
        academy_id="test-academy",
    )

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
