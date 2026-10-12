"""Integration acceptance: canonical Phase 4 migration and runtime adapter share one contract."""
from datetime import datetime, timedelta, timezone
from pathlib import Path

import persistence
import phase4_identity_store as store


def main() -> None:
    assert persistence.is_postgres_enabled(), "This acceptance test requires disposable PostgreSQL"
    migration = Path("migrations/20261012_phase4_identity_consent_canonical.sql").read_text()
    # Reset only dedicated Phase 4 identity/consent tables in this disposable CI database.
    with persistence.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DROP TABLE IF EXISTS kaizo_authorization_audit, kaizo_child_consents, "
                "kaizo_guardian_relationships, kaizo_resource_tenant_bindings, "
                "kaizo_tenant_memberships, kaizo_tenants CASCADE"
            )
            cur.execute(migration)
            cur.execute(
                "INSERT INTO kaizo_tenants (tenant_id, display_name) "
                "VALUES (%s, %s) ON CONFLICT (tenant_id) DO NOTHING",
                ("phase4-it-academy", "Phase 4 integration test academy"),
            )
        conn.commit()

    try:
        store.record_membership(
            membership_id="phase4-it-member-v1", actor_id="phase4-it-coach",
            academy_id="phase4-it-academy", role="coach", status="active",
            version=1, resource_owner_id="phase4-it-coach",
        )
        assert store.has_active_membership(
            actor_id="phase4-it-coach", academy_id="phase4-it-academy", role="coach"
        )
        assert not store.has_active_membership(
            actor_id="phase4-it-coach", academy_id="other-tenant", role="coach"
        )
        store.record_membership(
            membership_id="phase4-it-member-v2", actor_id="phase4-it-coach",
            academy_id="phase4-it-academy", role="coach", status="revoked",
            version=2, resource_owner_id="phase4-it-coach",
        )
        assert not store.has_active_membership(
            actor_id="phase4-it-coach", academy_id="phase4-it-academy", role="coach"
        )

        now = datetime.now(timezone.utc)
        store.record_guardian_relationship(
            relationship_id="phase4-it-guardian-v1", child_id="phase4-it-child",
            guardian_actor_id="phase4-it-guardian", academy_id="phase4-it-academy",
            verification_status="verified", version=1,
            verified_by="phase4-it-authoritative-verifier", verified_at=now,
        )
        assert store.has_verified_guardian_relationship(
            child_id="phase4-it-child", guardian_actor_id="phase4-it-guardian",
            academy_id="phase4-it-academy",
        )
        store.record_guardian_relationship(
            relationship_id="phase4-it-guardian-v2", child_id="phase4-it-child",
            guardian_actor_id="phase4-it-guardian", academy_id="phase4-it-academy",
            verification_status="revoked", version=2,
        )
        assert not store.has_verified_guardian_relationship(
            child_id="phase4-it-child", guardian_actor_id="phase4-it-guardian",
            academy_id="phase4-it-academy",
        )

        store.record_child_consent(
            consent_id="phase4-it-consent-v1", child_id="phase4-it-child",
            guardian_actor_id="phase4-it-guardian", academy_id="phase4-it-academy",
            resource="training_plan", action="read", state="active",
            expires_at=now + timedelta(days=1),
            recorded_by_actor_id="phase4-it-guardian", version=1,
        )
        assert store.has_active_child_consent(
            child_id="phase4-it-child", guardian_actor_id="phase4-it-guardian",
            academy_id="phase4-it-academy", resource="training_plan", action="read",
        )
        store.record_child_consent(
            consent_id="phase4-it-consent-v2", child_id="phase4-it-child",
            guardian_actor_id="phase4-it-guardian", academy_id="phase4-it-academy",
            resource="training_plan", action="read", state="revoked",
            expires_at=now + timedelta(days=1),
            recorded_by_actor_id="phase4-it-guardian", version=2,
        )
        assert not store.has_active_child_consent(
            child_id="phase4-it-child", guardian_actor_id="phase4-it-guardian",
            academy_id="phase4-it-academy", resource="training_plan", action="read",
        )
        store.record_child_consent(
            consent_id="phase4-it-consent-expired", child_id="phase4-it-child",
            guardian_actor_id="phase4-it-guardian", academy_id="phase4-it-academy",
            resource="assessment", action="read", state="active",
            expires_at=now - timedelta(seconds=1),
            recorded_by_actor_id="phase4-it-guardian", version=1,
        )
        assert not store.has_active_child_consent(
            child_id="phase4-it-child", guardian_actor_id="phase4-it-guardian",
            academy_id="phase4-it-academy", resource="assessment", action="read",
        )

        store.append_authorization_audit(
            event_id="phase4-it-audit-1", correlation_id="phase4-it-correlation",
            actor_id="phase4-it-coach", actor_role="coach", academy_id="phase4-it-academy",
            resource_type="training_plan", resource_id="phase4-it-plan", action="read",
            decision="deny", reason_code="CONSENT_REVOKED",
            consent_id="phase4-it-consent-v2", policy_version="phase4-it-policy-v1",
            request_route="/api/v1/training-plans/phase4-it-plan",
        )
        audit = store.list_authorization_audit(correlation_id="phase4-it-correlation")
        assert len(audit) == 1
        assert audit[0]["decision"] == "deny"
        assert audit[0]["reason_code"] == "CONSENT_REVOKED"
        print("PHASE 4 CANONICAL MIGRATION + IDENTITY STORE INTEGRATION PASS")
    finally:
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM kaizo_authorization_audit WHERE correlation_id=%s",
                    ("phase4-it-correlation",),
                )
                cur.execute(
                    "DELETE FROM kaizo_child_consents WHERE child_id=%s",
                    ("phase4-it-child",),
                )
                cur.execute(
                    "DELETE FROM kaizo_guardian_relationships WHERE child_id=%s",
                    ("phase4-it-child",),
                )
                cur.execute(
                    "DELETE FROM kaizo_tenant_memberships WHERE actor_id=%s",
                    ("phase4-it-coach",),
                )
                cur.execute(
                    "DELETE FROM kaizo_tenants WHERE tenant_id=%s",
                    ("phase4-it-academy",),
                )
            conn.commit()


if __name__ == "__main__":
    main()
