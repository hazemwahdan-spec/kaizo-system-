"""Tenant-scoped audit endpoint regression tests."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from phase4_identity_boundary import Principal


class AuditCursor:
    def __init__(self):
        self.query = ""
        self.params = ()
        self.description = [("event_id",), ("tenant_id",), ("event_type",)]
        self.rows = [("event-A", "tenant-A", "authorization_decision")]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params or ()

    def fetchall(self):
        return self.rows


class AuditConnection:
    def __init__(self):
        self.cursor_value = AuditCursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_value


class TenantScopedAuditEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.principal = Principal(
            actor_id="auth0|coach-A", role="coach", tenant_id="tenant-A",
            resource_owner_id=None, verified=True, source="oidc_jwt",
        )
        self.previous_override = main.app.dependency_overrides.get(main.require_phase4_principal)
        main.app.dependency_overrides[main.require_phase4_principal] = lambda: self.principal

    def tearDown(self):
        if self.previous_override is None:
            main.app.dependency_overrides.pop(main.require_phase4_principal, None)
        else:
            main.app.dependency_overrides[main.require_phase4_principal] = self.previous_override

    def test_audit_query_is_filtered_by_verified_tenant(self):
        connection = AuditConnection()
        with patch.object(main.persistence, "is_postgres_enabled", return_value=True), \
             patch.object(main.persistence, "connection", return_value=connection):
            response = self.client.get("/api/v1/audit/logs", headers={"Authorization": "Bearer test-only"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tenant_id"], "tenant-A")
        self.assertEqual(response.json()["logs"], [
            {"event_id": "event-A", "tenant_id": "tenant-A", "event_type": "authorization_decision"}
        ])
        self.assertIn("WHERE tenant_id=%s", connection.cursor_value.query)
        self.assertEqual(connection.cursor_value.params, ("tenant-A",))

    def test_audit_endpoint_fails_closed_without_postgres(self):
        with patch.object(main.persistence, "is_postgres_enabled", return_value=False):
            response = self.client.get("/api/v1/audit/logs", headers={"Authorization": "Bearer test-only"})
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
