"""Unit tests for the isolated Phase 4 tenant/consent repository candidate."""
import unittest
from unittest.mock import patch

import phase4_tenant_consent as module


class FakeCursor:
    def __init__(self, rows):
        self.rows = list(rows)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None


class FakeConnection:
    def __init__(self, rows):
        self.fake_cursor = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.fake_cursor


class Phase4TenantConsentRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.principal = {"verified": True, "source": "oidc_jwt", "actor_id": "auth0|coach-1"}
        self.scope = {
            "principal": self.principal,
            "tenant_id": "academy-1",
            "resource_type": "athlete",
            "resource_id": "athlete-1",
            "allowed_roles": ["coach"],
            "action": "read",
            "trace_id": "trace-test-1",
        }

    def test_unverified_principal_is_denied_without_database_access(self):
        with patch.object(module.persistence, "is_postgres_enabled") as enabled:
            result = module.authorize_resource_access(
                **{**self.scope, "principal": {"sub": "client-supplied"}}
            )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason_code"], "verified_oidc_principal_required")
        enabled.assert_not_called()

    def test_postgres_disabled_fails_closed(self):
        with patch.object(module.persistence, "is_postgres_enabled", return_value=False):
            with self.assertRaises(module.Phase4AuthorizationUnavailable):
                module.authorize_resource_access(**self.scope)

    def test_active_membership_and_binding_allow_and_write_audit(self):
        connection = FakeConnection([(1,), (1,)])
        with patch.object(module.persistence, "is_postgres_enabled", return_value=True), \
             patch.object(module.persistence, "connection", return_value=connection):
            result = module.authorize_resource_access(**self.scope)
        self.assertTrue(result["allowed"])
        self.assertTrue(result["audit_persisted"])
        self.assertIn("INSERT INTO kaizo_p14_audit_events",
                      connection.fake_cursor.statements[-1][0])

    def test_missing_binding_denies_and_writes_audit(self):
        connection = FakeConnection([(1,), None])
        with patch.object(module.persistence, "is_postgres_enabled", return_value=True), \
             patch.object(module.persistence, "connection", return_value=connection):
            result = module.authorize_resource_access(**self.scope)
        self.assertFalse(result["allowed"])
        self.assertEqual(
            result["reason_code"], "resource_tenant_binding_missing_or_mismatched"
        )
        self.assertIn("INSERT INTO kaizo_p14_audit_events",
                      connection.fake_cursor.statements[-1][0])

    def test_child_scope_without_identifier_denies(self):
        result = module.authorize_resource_access(
            **{**self.scope, "requires_guardian_consent": True}
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason_code"], "child_scope_required")

    def test_missing_guardian_consent_denies(self):
        connection = FakeConnection([(1,), (1,), None])
        with patch.object(module.persistence, "is_postgres_enabled", return_value=True), \
             patch.object(module.persistence, "connection", return_value=connection):
            result = module.authorize_resource_access(
                **{**self.scope, "requires_guardian_consent": True,
                   "child_resource_id": "athlete-1"}
            )
        self.assertFalse(result["allowed"])
        self.assertEqual(
            result["reason_code"], "verified_guardian_or_active_consent_missing"
        )

    def test_verified_guardian_and_active_scoped_consent_allow(self):
        connection = FakeConnection([(1,), (1,), ("auth0|guardian-1",)])
        with patch.object(module.persistence, "is_postgres_enabled", return_value=True), \
             patch.object(module.persistence, "connection", return_value=connection):
            result = module.authorize_resource_access(
                **{**self.scope, "requires_guardian_consent": True,
                   "child_resource_id": "athlete-1"}
            )
        self.assertTrue(result["allowed"])
        self.assertEqual(result["reason_code"], "verified_guardian_active_scoped_consent")
        self.assertTrue(result["audit_persisted"])


if __name__ == "__main__":
    unittest.main()
