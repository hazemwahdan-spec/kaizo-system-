"""Actual FastAPI route denial tests for Phase 4 tenant and P14 consent gates.

The HTTP stack and decorated Core API route are real. The database cursor is
isolated so these tests are deterministic; PostgreSQL schema/SQL validation is
run separately in the persistence workflow.
"""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
import phase4_route_guard
from phase4_identity_boundary import Principal


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
        self.cursor_value = FakeCursor(rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return self.cursor_value


class Phase4RouteAuthorizationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.principal = Principal(
            actor_id="auth0|coach-1",
            role="coach",
            tenant_id="academy-A",
            resource_owner_id=None,
            verified=True,
            source="oidc_jwt",
        )
        self.payload = {
            "athlete_id": "athlete-1",
            "template_id": "baseline",
            "measurements": {"seoi_nage_entry": 4},
            "recorded_by": "auth0|coach-1",
        }
        self.athlete = {
            "athlete_id": "athlete-1",
            "metadata": {"is_minor": True},
        }

    def _post(self, rows, payload=None):
        connection = FakeConnection(rows)
        with patch.object(phase4_route_guard, "require_phase4_principal",
                          return_value=self.principal), \
             patch.object(phase4_route_guard.persistence, "is_postgres_enabled",
                          return_value=True), \
             patch.object(phase4_route_guard.persistence, "connection",
                          return_value=connection), \
             patch.object(phase4_route_guard.persistence, "get_athlete",
                          return_value=self.athlete):
            response = self.client.post(
                "/api/v1/assessments",
                json=payload or self.payload,
                headers={"Authorization": "Bearer test-token", "X-Trace-Id": "trace-route-test"},
            )
        return response, connection.cursor_value

    def test_caller_supplied_actor_id_is_rejected_before_database_access(self):
        payload = dict(self.payload)
        payload["recorded_by"] = "untrusted-body-actor"
        response, cursor = self._post([], payload=payload)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "actor_identity_mismatch",
        )
        self.assertEqual(cursor.statements, [])

    def test_cross_tenant_resource_binding_is_denied_by_real_route(self):
        response, cursor = self._post([(1,), None])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "resource_tenant_binding_missing_or_mismatched",
        )
        self.assertTrue(any("INSERT INTO kaizo_p14_audit_events" in sql
                            for sql, _ in cursor.statements))

    def test_missing_guardian_consent_is_denied_by_real_route(self):
        response, cursor = self._post([(1,), (1,), None])
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "verified_guardian_or_active_consent_missing",
        )
        consent_sql = next(sql for sql, _ in cursor.statements
                           if "FROM kaizo_guardian_relationships gr" in sql)
        self.assertIn("c.state='active'", consent_sql)
        self.assertIn("c.recorded_by_subject=c.guardian_subject_id", consent_sql)
        self.assertTrue(any("INSERT INTO kaizo_p14_audit_events" in sql
                            for sql, _ in cursor.statements))

    def test_revoked_or_superseded_consent_is_denied_by_real_route(self):
        # A revoked latest row cannot satisfy the SQL predicate for active
        # consent, and the NOT EXISTS predicate excludes older active rows.
        response, cursor = self._post([(1,), (1,), None])
        self.assertEqual(response.status_code, 403)
        consent_sql = next(sql for sql, _ in cursor.statements
                           if "FROM kaizo_guardian_relationships gr" in sql)
        self.assertIn("c.state='active'", consent_sql)
        self.assertIn("NOT EXISTS", consent_sql)
        self.assertIn("newer.recorded_sequence > c.recorded_sequence", consent_sql)

    def test_unbound_digital_twin_rejects_body_supplied_owner(self):
        from fastapi import HTTPException
        request = type("RequestStub", (), {"path_params": {"entity_id": "unbound-twin"}, "query_params": {}})()
        with patch.object(phase4_route_guard.persistence, "get_athlete", return_value=None), \
             patch.object(phase4_route_guard.persistence, "get_digital_twin", return_value=None):
            with self.assertRaises(HTTPException) as raised:
                phase4_route_guard._resolve_athlete_id(request, {"state": {"athlete_id": "athlete-1"}})
        self.assertEqual(raised.exception.status_code, 403)
        self.assertIn("persisted athlete ownership", raised.exception.detail)

    def test_unverified_principal_is_denied_before_database_access(self):
        connection = FakeConnection([])
        with patch.object(phase4_route_guard, "require_phase4_principal",
                          side_effect=__import__("fastapi").HTTPException(
                              status_code=401, detail="A valid OIDC bearer identity is required"
                          )), \
             patch.object(phase4_route_guard.persistence, "is_postgres_enabled",
                          return_value=True), \
             patch.object(phase4_route_guard.persistence, "connection",
                          return_value=connection):
            response = self.client.post(
                "/api/v1/assessments",
                json=self.payload,
                headers={"Authorization": "Bearer invalid"},
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(connection.cursor_value.statements, [])


if __name__ == "__main__":
    unittest.main()
