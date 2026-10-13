import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from main import app, ATHLETE_RECORDS, ASSESSMENT_RECORDS, AUDIT_LOGS
from phase4_core_resource_authorization import require_core_actor
from productization.identity import Principal


class FEAT012RecordAthleteAssessmentTests(unittest.TestCase):
    def setUp(self):
        ATHLETE_RECORDS.clear()
        ASSESSMENT_RECORDS.clear()
        AUDIT_LOGS.clear()
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
        self.addCleanup(self._cleanup_auth)
        self.client = TestClient(app)

    def _cleanup_auth(self):
        app.dependency_overrides.pop(require_core_actor, None)
        for item in reversed(self._auth_patches):
            item.stop()

    def _athlete(self):
        response = self.client.post(
            "/api/v1/athletes",
            json={"display_name": "FEAT012 Athlete"},
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    def test_record_assessment_preserves_ownership_template_measurements_and_timestamps(self):
        athlete = self._athlete()
        response = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": athlete["athlete_id"],
                "template_id": "ASSESSMENT-U11-GRIP",
                "measurements": {"grip_strength_kg": 18.5, "entry_quality": 7},
                "recorded_by": "coach-feat012",
            },
        )
        self.assertEqual(response.status_code, 201)
        assessment = response.json()

        self.assertTrue(assessment["assessment_id"])
        self.assertEqual(assessment["athlete_id"], athlete["athlete_id"])
        self.assertEqual(assessment["template_id"], "ASSESSMENT-U11-GRIP")
        self.assertEqual(assessment["measurements"]["grip_strength_kg"], 18.5)
        self.assertEqual(assessment["recorded_by"], "coach-feat012")
        self.assertTrue(assessment["assessed_at"])
        self.assertTrue(assessment["created_at"])

    def test_recorded_assessment_is_readable_by_stable_id(self):
        athlete = self._athlete()
        created = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": athlete["athlete_id"],
                "template_id": "ASSESSMENT-U11-GRIP",
                "measurements": {"score": 7},
                "recorded_by": "coach-feat012",
            },
        )
        self.assertEqual(created.status_code, 201)
        assessment = created.json()

        fetched = self.client.get(f"/api/v1/assessments/{assessment['assessment_id']}")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), assessment)

    def test_assessment_requires_existing_athlete_and_measurements(self):
        missing_athlete = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": "ATHLETE-FEAT012-MISSING",
                "template_id": "ASSESSMENT-U11-GRIP",
                "measurements": {"score": 7},
                "recorded_by": "coach-feat012",
            },
        )
        self.assertEqual(missing_athlete.status_code, 404)

        athlete = self._athlete()
        missing_measurements = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": athlete["athlete_id"],
                "template_id": "ASSESSMENT-U11-GRIP",
                "measurements": {},
                "recorded_by": "coach-feat012",
            },
        )
        self.assertEqual(missing_measurements.status_code, 400)

    def test_assessment_recording_is_audited(self):
        athlete = self._athlete()
        response = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": athlete["athlete_id"],
                "template_id": "ASSESSMENT-U11-GRIP",
                "measurements": {"score": 8},
                "recorded_by": "coach-feat012",
            },
        )
        self.assertEqual(response.status_code, 201)

        audit = self.client.get("/api/v1/audit/logs")
        self.assertEqual(audit.status_code, 200)
        matches = [x for x in audit.json()["logs"] if x["action"] == "ASSESSMENT_RECORDED"]
        self.assertTrue(matches)
        self.assertEqual(matches[-1]["who"], "coach-feat012")
        self.assertEqual(matches[-1]["new_value"]["athlete_id"], athlete["athlete_id"])
        self.assertEqual(matches[-1]["new_value"]["template_id"], "ASSESSMENT-U11-GRIP")


if __name__ == "__main__":
    unittest.main()
