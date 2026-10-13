import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app, ATHLETE_RECORDS, ASSESSMENT_RECORDS
from phase4_core_resource_authorization import require_core_actor
from productization.identity import Principal


class TestOnlyCoreAuthOverrides:
    def _install_core_auth_overrides(self):
        self.principal = Principal(
            actor_id="unit-test-coach", role="coach", tenant_id="unit-test-academy",
            resource_owner_id=None, verified=True, source="test_override",
        )
        app.dependency_overrides[require_core_actor] = lambda: self.principal
        self._auth_patches = [
            patch("main.bind_new_resource"),
            patch("main.assert_resource_tenant"),
            patch("main.assert_assessment_tenant"),
            patch("main.assert_minor_consent"),
        ]
        for item in self._auth_patches:
            item.start()

    def _remove_core_auth_overrides(self):
        app.dependency_overrides.pop(require_core_actor, None)
        for item in reversed(getattr(self, "_auth_patches", [])):
            item.stop()


class FEAT011MeasurementPersistenceTests(TestOnlyCoreAuthOverrides, unittest.TestCase):
    def setUp(self):
        ATHLETE_RECORDS.clear()
        ASSESSMENT_RECORDS.clear()
        self._install_core_auth_overrides()
        self.addCleanup(self._remove_core_auth_overrides)
        self.client = TestClient(app)

    def test_assessment_is_created_and_read_with_owner_and_timestamps(self):
        athlete = self.client.post(
            "/api/v1/athletes",
            json={"display_name": "Assessment Athlete"},
        )
        self.assertEqual(athlete.status_code, 201)
        athlete_id = athlete.json()["athlete_id"]

        created = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": athlete_id,
                "template_id": "ASSESSMENT-U11-GRIP",
                "measurements": {"grip_strength_kg": 18.5},
                "recorded_by": "coach-001",
            },
        )
        self.assertEqual(created.status_code, 201)
        assessment = created.json()
        self.assertTrue(assessment["assessment_id"])
        self.assertEqual(assessment["athlete_id"], athlete_id)
        self.assertEqual(assessment["recorded_by"], "coach-001")
        self.assertEqual(assessment["measurements"]["grip_strength_kg"], 18.5)
        self.assertTrue(assessment["assessed_at"])
        self.assertTrue(assessment["created_at"])

        fetched = self.client.get(
            f"/api/v1/assessments/{assessment['assessment_id']}"
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), assessment)

    def test_assessment_requires_existing_athlete(self):
        response = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": "missing-athlete",
                "template_id": "ASSESSMENT-U11-GRIP",
                "measurements": {"grip_strength_kg": 18.5},
                "recorded_by": "coach-001",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_assessment_requires_measurements(self):
        athlete = self.client.post(
            "/api/v1/athletes",
            json={"display_name": "Assessment Athlete"},
        )
        athlete_id = athlete.json()["athlete_id"]

        response = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": athlete_id,
                "template_id": "ASSESSMENT-U11-GRIP",
                "measurements": {},
                "recorded_by": "coach-001",
            },
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()


class FEAT046AuditSpineTests(TestOnlyCoreAuthOverrides, unittest.TestCase):
    def setUp(self):
        self._install_core_auth_overrides()
        self.addCleanup(self._remove_core_auth_overrides)

    def test_assessment_action_is_written_to_audit_spine(self):
        ATHLETE_RECORDS.clear()
        ASSESSMENT_RECORDS.clear()
        client = TestClient(app)

        athlete = client.post("/api/v1/athletes", json={"display_name": "Audit Athlete"})
        self.assertEqual(athlete.status_code, 201)

        created = client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": athlete.json()["athlete_id"],
                "template_id": "AUDIT-SPINE",
                "measurements": {"score": 7},
                "recorded_by": "coach-audit",
            },
        )
        self.assertEqual(created.status_code, 201)

        audit = client.get("/api/v1/audit/logs")
        self.assertEqual(audit.status_code, 200)
        matching = [x for x in audit.json()["logs"] if x["action"] == "ASSESSMENT_RECORDED"]
        self.assertTrue(matching)
        self.assertEqual(matching[-1]["who"], "coach-audit")
        self.assertEqual(matching[-1]["new_value"]["athlete_id"], athlete.json()["athlete_id"])
        self.assertEqual(matching[-1]["why"], "Assessment measurements persisted with explicit athlete ownership and timestamp.")

    def test_audit_log_preserves_old_and_new_values(self):
        client = TestClient(app)
        response = client.get("/api/v1/audit/logs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("logs", response.json())
        for entry in response.json()["logs"]:
            self.assertIn("timestamp", entry)
            self.assertIn("who", entry)
            self.assertIn("action", entry)
            self.assertIn("old_value", entry)
            self.assertIn("new_value", entry)
            self.assertIn("why", entry)
