import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app, ATHLETE_RECORDS
from phase4_core_resource_authorization import (
    require_core_actor,
)
from productization.identity import Principal


class FEAT001AthleteRecordTests(unittest.TestCase):
    def setUp(self):
        ATHLETE_RECORDS.clear()
        self.principal = Principal(
            actor_id="unit-test-coach", role="coach", tenant_id="unit-test-academy",
            resource_owner_id=None, verified=True, source="test_override",
        )
        app.dependency_overrides[require_core_actor] = lambda: self.principal
        self._binding_patches = [
            patch("main.bind_new_resource"),
            patch("main.assert_resource_tenant"),
            patch("main.assert_assessment_tenant"),
            patch("main.assert_minor_consent"),
        ]
        for item in self._binding_patches:
            item.start()
        self.addCleanup(self._cleanup_authorization_patches)
        self.client = TestClient(app)

    def _cleanup_authorization_patches(self):
        app.dependency_overrides.pop(require_core_actor, None)
        for item in reversed(self._binding_patches):
            item.stop()

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
