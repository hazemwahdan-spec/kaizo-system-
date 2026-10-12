"""HTTP tests against backend.main:app for the protected athlete resource route."""
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from phase4_identity_boundary import Principal


class Phase4AthleteRouteEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.coach = Principal(
            actor_id="auth0|coach-1", role="coach", tenant_id="academy-1",
            resource_owner_id=None, verified=True, source="oidc_jwt",
        )
        self.parent = Principal(
            actor_id="auth0|guardian-1", role="parent", tenant_id="academy-1",
            resource_owner_id=None, verified=True, source="oidc_jwt",
        )
        main.app.dependency_overrides[main.require_phase4_principal] = lambda: self.coach

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_identity_gate_disabled_fails_closed(self):
        main.app.dependency_overrides.clear()
        with patch.dict(os.environ, {"KAIZO_PHASE4_IDENTITY_ENFORCEMENT": "disabled"}):
            response = self.client.get("/api/v1/athletes/athlete-1")
        self.assertEqual(response.status_code, 503)

    def test_missing_bearer_token_is_rejected_when_oidc_gate_enabled(self):
        main.app.dependency_overrides.clear()
        with patch.dict(os.environ, {"KAIZO_PHASE4_IDENTITY_ENFORCEMENT": "oidc"}):
            response = self.client.get("/api/v1/athletes/athlete-1")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get("www-authenticate"), "Bearer")

    def test_cross_tenant_or_missing_resource_binding_is_denied_before_read(self):
        with patch(
            "phase4_route_guard.authorize_resource_access",
            return_value={
                "allowed": False,
                "reason_code": "resource_tenant_binding_missing_or_mismatched",
                "audit_persisted": True,
                "trace_id": "trace-cross-tenant",
            },
        ), patch("main.persistence.get_athlete") as get_athlete:
            response = self.client.get("/api/v1/athletes/athlete-foreign")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "resource_tenant_binding_missing_or_mismatched",
        )
        get_athlete.assert_not_called()

    def test_parent_without_consent_is_denied_before_read(self):
        main.app.dependency_overrides[main.require_phase4_principal] = lambda: self.parent
        with patch(
            "phase4_route_guard.authorize_resource_access",
            return_value={
                "allowed": False,
                "reason_code": "verified_guardian_or_active_consent_missing",
                "audit_persisted": True,
                "trace_id": "trace-no-consent",
            },
        ) as authorize, patch("main.persistence.get_athlete") as get_athlete:
            response = self.client.get("/api/v1/athletes/child-1")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["reason_code"],
            "verified_guardian_or_active_consent_missing",
        )
        self.assertTrue(authorize.call_args.kwargs["requires_guardian_consent"])
        get_athlete.assert_not_called()

    def test_parent_with_revoked_consent_is_denied_before_read(self):
        main.app.dependency_overrides[main.require_phase4_principal] = lambda: self.parent
        with patch(
            "phase4_route_guard.authorize_resource_access",
            return_value={
                "allowed": False,
                "reason_code": "verified_guardian_or_active_consent_missing",
                "audit_persisted": True,
                "trace_id": "trace-revoked-consent",
            },
        ), patch("main.persistence.get_athlete") as get_athlete:
            response = self.client.get("/api/v1/athletes/child-1")
        self.assertEqual(response.status_code, 403)
        get_athlete.assert_not_called()

    def test_parent_cannot_update_athlete_even_with_read_consent(self):
        main.app.dependency_overrides[main.require_phase4_principal] = lambda: self.parent
        with patch("phase4_route_guard.authorize_resource_access") as authorize, \
             patch("main.persistence.get_athlete") as get_athlete:
            response = self.client.patch(
                "/api/v1/athletes/child-1", json={"status": "INACTIVE"}
            )
        self.assertEqual(response.status_code, 403)
        authorize.assert_not_called()
        get_athlete.assert_not_called()

    def test_authorization_backend_failure_fails_closed(self):
        with patch(
            "phase4_route_guard.authorize_resource_access",
            side_effect=RuntimeError("database unavailable"),
        ), patch("main.persistence.get_athlete") as get_athlete:
            response = self.client.get("/api/v1/athletes/athlete-1")
        self.assertEqual(response.status_code, 503)
        get_athlete.assert_not_called()

    def test_successful_scoped_authorization_allows_record_read(self):
        with patch(
            "phase4_route_guard.authorize_resource_access",
            return_value={
                "allowed": True,
                "reason_code": "active_membership_and_resource_binding",
                "audit_persisted": True,
                "trace_id": "trace-allow",
            },
        ), patch("main.persistence.is_postgres_enabled", return_value=True), patch(
            "main.persistence.get_athlete",
            return_value={"athlete_id": "athlete-1", "display_name": "Test athlete"},
        ):
            response = self.client.get("/api/v1/athletes/athlete-1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["athlete_id"], "athlete-1")


if __name__ == "__main__":
    unittest.main()
