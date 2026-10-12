import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import main
from main import app, ATHLETE_RECORDS
from phase4_identity_boundary import Principal


class FEAT001AthleteRecordTests(unittest.TestCase):
    def setUp(self):
        ATHLETE_RECORDS.clear()
        self.client = TestClient(app)
        principal = Principal(
            actor_id="auth0|test-coach", role="coach", tenant_id="test-academy",
            resource_owner_id=None, verified=True, source="oidc_jwt",
        )
        app.dependency_overrides[main.require_phase4_principal] = lambda: principal
        self.authorization_patch = patch(
            "phase4_route_guard.authorize_resource_access",
            return_value={
                "allowed": True,
                "reason_code": "active_membership_and_resource_binding",
                "audit_persisted": True,
                "trace_id": "trace-feat-001-test",
            },
        )
        self.authorization_patch.start()
        self.create_patch = patch(\n            "main.create_athlete_with_tenant",\n            side_effect=lambda principal, athlete: main.persistence.upsert_athlete(athlete),\n        )
        self.create_patch.start()

    def tearDown(self):
        self.create_patch.stop()
        self.authorization_patch.stop()
        app.dependency_overrides.clear()

    def test_create_read_and_update_athlete(self):
        created = self.client.post(
            "/api/v1/athletes",
            json={"display_name": "Test Athlete", "metadata": {"age_group": "U11"}},
        )
        self.assertEqual(created.status_code, 201)
        athlete = created.json()
        self.assertTrue(athlete["athlete_id"])
        self.assertEqual(athlete["status"], "ACTIVE")
        stable_id = athlete["athlete_id"]

        fetched = self.client.get(f"/api/v1/athletes/{stable_id}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["athlete_id"], stable_id)

        updated = self.client.patch(
            f"/api/v1/athletes/{stable_id}",
            json={"status": "INACTIVE"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["athlete_id"], stable_id)
        self.assertEqual(updated.json()["status"], "INACTIVE")

    def test_invalid_lifecycle_status_is_blocked(self):
        created = self.client.post(
            "/api/v1/athletes",
            json={"display_name": "Test Athlete"},
        )
        athlete_id = created.json()["athlete_id"]

        blocked = self.client.patch(
            f"/api/v1/athletes/{athlete_id}",
            json={"status": "INVALID"},
        )
        self.assertEqual(blocked.status_code, 400)

    def test_missing_athlete_is_404(self):
        response = self.client.get("/api/v1/athletes/does-not-exist")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
