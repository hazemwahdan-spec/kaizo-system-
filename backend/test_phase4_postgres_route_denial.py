"""PostgreSQL-backed Phase 4 route denial tests.

Runs after the disposable PostgreSQL migration step in CI. Only OIDC resolution
is stubbed; membership, resource ownership, guardian, consent and audit checks
execute against the real test database.
"""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import persistence
import phase4_route_guard
from phase4_identity_boundary import Principal


@unittest.skipUnless(
    os.getenv("KAIZO_PERSISTENCE_MODE", "").strip().lower() == "postgres",
    "requires the disposable PostgreSQL integration environment",
)
class Phase4PostgresRouteDenialTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        suffix = uuid4().hex
        self.tenant_a = "tenant-a-" + suffix
        self.tenant_b = "tenant-b-" + suffix
        self.subject = "auth0|coach-" + suffix
        self.guardian = "auth0|guardian-" + suffix
        self.athlete_id = "athlete-" + suffix
        self.event_id = "event-" + suffix
        self.trace_id = "p4-route-" + suffix
        self.principal = Principal(
            actor_id=self.subject, role="coach", tenant_id=self.tenant_a,
            resource_owner_id=None, verified=True, source="oidc_jwt",
        )
        self.athlete = {"athlete_id": self.athlete_id, "metadata": {"is_minor": True}}
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO kaizo_tenants(tenant_id,display_name) VALUES (%s,%s),(%s,%s)",
                    (self.tenant_a, self.tenant_a, self.tenant_b, self.tenant_b),
                )
                cur.execute(
                    """INSERT INTO kaizo_tenant_memberships(tenant_id,subject_id,role,status)
                       VALUES (%s,%s,'coach','ACTIVE')""",
                    (self.tenant_a, self.subject),
                )
                cur.execute(
                    """INSERT INTO kaizo_resource_tenant_bindings
                       (resource_type,resource_id,tenant_id,bound_by_subject)
                       VALUES ('athlete',%s,%s,%s),('competition_event',%s,%s,%s)""",
                    (self.athlete_id, self.tenant_a, self.subject,
                     self.event_id, self.tenant_a, self.subject),
                )
                cur.execute(
                    """INSERT INTO kaizo_guardian_relationships
                       (child_resource_id,guardian_subject_id,tenant_id,relationship_type,
                        verification_status,verified_by_subject,verified_at)
                       VALUES (%s,%s,%s,'parent','VERIFIED',%s,NOW())""",
                    (self.athlete_id, self.guardian, self.tenant_a, self.subject),
                )
            conn.commit()

    def _request(self, trace_suffix, principal=None, domain_route=False):
        if domain_route:
            path = f"/api/v1/competition/readiness/{self.athlete_id}/{self.event_id}"
        else:
            path = f"/api/v1/athletes/{self.athlete_id}"
        with patch.object(phase4_route_guard, "require_phase4_principal",
                          return_value=principal or self.principal), \
             patch.object(phase4_route_guard.persistence, "get_athlete",
                          return_value=self.athlete):
            return self.client.get(
                path,
                headers={"Authorization": "Bearer test-token",
                         "X-Trace-Id": self.trace_id + trace_suffix},
            )

    def _insert_consent(self, state, created_at_sql="NOW()", expires_at_sql="NULL"):
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""INSERT INTO kaizo_p14_consents
                        (child_resource_id,guardian_subject_id,tenant_id,resource_type,
                         action,state,recorded_by_subject,created_at,expires_at)
                        VALUES (%s,%s,%s,'athlete','GET:/api/v1/athletes/{{athlete_id}}',%s,%s,{created_at_sql},{expires_at_sql})""",
                    (self.athlete_id, self.guardian, self.tenant_a, state, self.guardian),
                )
            conn.commit()

    def test_cross_tenant_binding_is_denied_and_audited(self):
        # Reassign the existing binding to another academy in the test DB.
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE kaizo_resource_tenant_bindings SET tenant_id=%s
                       WHERE resource_type='athlete' AND resource_id=%s""",
                    (self.tenant_b, self.athlete_id),
                )
            conn.commit()
        response = self._request("-cross-tenant")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "resource_tenant_binding_missing_or_mismatched",
        )
        self._assert_audit(self.trace_id + "-cross-tenant", False)

    def test_active_scoped_consent_allows_route_and_is_audited(self):
        self._insert_consent("active")
        response = self._request("-active")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["athlete_id"], self.athlete_id)
        self._assert_audit(self.trace_id + "-active", True)

    def test_missing_guardian_consent_is_denied_and_audited(self):
        response = self._request("-no-consent")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "verified_guardian_or_active_consent_missing",
        )
        self._assert_audit(self.trace_id + "-no-consent", False)

    def test_revoked_newest_consent_supersedes_older_active_consent(self):
        self._insert_consent("active", "'2026-01-01T00:00:00+00:00'::timestamptz")
        self._insert_consent("revoked", "'2026-01-02T00:00:00+00:00'::timestamptz")
        response = self._request("-revoked")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "verified_guardian_or_active_consent_missing",
        )
        self._assert_audit(self.trace_id + "-revoked", False)

    def test_expired_guardian_consent_is_denied_and_audited(self):
        self._insert_consent(
            "active",
            expires_at_sql="'2026-01-02T00:00:00+00:00'::timestamptz",
        )
        response = self._request("-expired")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "verified_guardian_or_active_consent_missing",
        )
        self._assert_audit(self.trace_id + "-expired", False)

    def test_parent_cannot_use_another_guardians_active_consent(self):
        self._insert_consent("active")
        other_parent = "auth0|other-parent-" + uuid4().hex
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO kaizo_tenant_memberships(tenant_id,subject_id,role,status)
                       VALUES (%s,%s,'parent','ACTIVE')""",
                    (self.tenant_a, other_parent),
                )
            conn.commit()
        parent_principal = Principal(
            actor_id=other_parent, role="parent", tenant_id=self.tenant_a,
            resource_owner_id=None, verified=True, source="oidc_jwt",
        )
        trace = self.trace_id + "-other-parent"
        from phase4_identity_boundary import require_phase4_principal
        previous = main.app.dependency_overrides.get(require_phase4_principal)
        main.app.dependency_overrides[require_phase4_principal] = lambda: parent_principal
        try:
            response = self._request("-other-parent", principal=parent_principal, domain_route=True)
        finally:
            if previous is None:
                main.app.dependency_overrides.pop(require_phase4_principal, None)
            else:
                main.app.dependency_overrides[require_phase4_principal] = previous
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "verified_guardian_or_active_consent_missing",
        )
        self._assert_audit(trace, False)

    def _assert_audit(self, trace_id, allowed):
        with persistence.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT allowed FROM kaizo_p14_audit_events WHERE trace_id=%s ORDER BY occurred_at DESC LIMIT 1",
                    (trace_id,),
                )
                row = cur.fetchone()
        self.assertIsNotNone(row, "authorization denial must have a durable audit event")
        self.assertEqual(row[0], allowed)


if __name__ == "__main__":
    unittest.main()
