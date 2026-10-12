"""PostgreSQL-backed integration tests for tenant and P14 consent enforcement.

These tests run only after the additive Phase 4 migration against the disposable
PostgreSQL service configured in persistence-adapter-validation.yml.
"""
import os
import unittest
import uuid
from datetime import datetime, timezone

import persistence
from phase4_tenant_consent import authorize_resource_access


@unittest.skipUnless(
    os.getenv("KAIZO_PERSISTENCE_MODE", "").strip().lower() == "postgres"
    and os.getenv("DATABASE_URL", "").strip(),
    "requires disposable PostgreSQL from persistence-adapter-validation workflow",
)
class Phase4TenantConsentPostgresTests(unittest.TestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex
        self.tenant = "p4-" + suffix
        self.other_tenant = "p4-other-" + suffix
        self.athlete = "athlete-" + suffix
        self.coach = "auth0|coach-" + suffix
        self.guardian = "auth0|guardian-" + suffix
        self.trace = "trace-" + suffix

        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO kaizo_tenants(tenant_id,display_name) VALUES (%s,%s),(%s,%s)",
                    (self.tenant, "Test academy", self.other_tenant, "Other academy"),
                )
                cur.execute(
                    """INSERT INTO kaizo_tenant_memberships
                       (tenant_id,subject_id,role,status)
                       VALUES (%s,%s,'parent','ACTIVE'),(%s,%s,'parent','ACTIVE')""",
                    (self.tenant, self.guardian, self.other_tenant, self.guardian),
                )
                cur.execute(
                    """INSERT INTO kaizo_resource_tenant_bindings
                       (resource_type,resource_id,tenant_id,bound_by_subject)
                       VALUES ('athlete',%s,%s,%s)""",
                    (self.athlete, self.tenant, self.coach),
                )
                cur.execute(
                    """INSERT INTO kaizo_guardian_relationships
                       (child_resource_id,guardian_subject_id,tenant_id,relationship_type,
                        verification_status,verified_by_subject,verified_at)
                       VALUES (%s,%s,%s,'parent','VERIFIED',%s,NOW())""",
                    (self.athlete, self.guardian, self.tenant, self.coach),
                )

        self.principal = {
            "verified": True, "source": "oidc_jwt", "actor_id": self.guardian,
        }

    def tearDown(self):
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM kaizo_p14_audit_events WHERE trace_id=%s", (self.trace,))
                cur.execute("DELETE FROM kaizo_p14_consents WHERE child_resource_id=%s", (self.athlete,))
                cur.execute("DELETE FROM kaizo_guardian_relationships WHERE child_resource_id=%s", (self.athlete,))
                cur.execute("DELETE FROM kaizo_resource_tenant_bindings WHERE resource_id=%s", (self.athlete,))
                cur.execute("DELETE FROM kaizo_tenant_memberships WHERE tenant_id IN (%s,%s)", (self.tenant,self.other_tenant))
                cur.execute("DELETE FROM kaizo_tenants WHERE tenant_id IN (%s,%s)", (self.tenant,self.other_tenant))

    def authorize(self, tenant_id=None):
        return authorize_resource_access(
            principal=self.principal,
            tenant_id=tenant_id or self.tenant,
            resource_type="athlete",
            resource_id=self.athlete,
            allowed_roles=["parent"],
            action="read",
            trace_id=self.trace,
            child_resource_id=self.athlete,
            requires_guardian_consent=True,
        )

    def insert_consent(self, state, when_sql="clock_timestamp()"):
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""INSERT INTO kaizo_p14_consents
                       (child_resource_id,guardian_subject_id,tenant_id,resource_type,
                        action,state,recorded_by_subject,created_at)
                       VALUES (%s,%s,%s,'athlete','read',%s,%s,{when_sql})""",
                    (self.athlete,self.guardian,self.tenant,state,self.coach),
                )

    def test_cross_tenant_resource_binding_is_denied_and_audited(self):
        result = self.authorize(tenant_id=self.other_tenant)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason_code"], "resource_tenant_binding_missing_or_mismatched")
        self.assertTrue(result["audit_persisted"])

    def test_missing_guardian_consent_is_denied_and_audited(self):
        result = self.authorize()
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason_code"], "verified_guardian_or_active_consent_missing")
        self.assertTrue(result["audit_persisted"])

    def test_revoked_consent_supersedes_older_active_consent(self):
        self.insert_consent("active", "clock_timestamp() - INTERVAL '1 minute'")
        self.insert_consent("revoked", "clock_timestamp()")
        result = self.authorize()
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason_code"], "verified_guardian_or_active_consent_missing")
        self.assertTrue(result["audit_persisted"])

    def test_active_scoped_consent_allows_and_is_audited(self):
        self.insert_consent("active")
        result = self.authorize()
        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason_code"], "verified_guardian_active_scoped_consent")
        self.assertTrue(result["audit_persisted"])


if __name__ == "__main__":
    unittest.main()
