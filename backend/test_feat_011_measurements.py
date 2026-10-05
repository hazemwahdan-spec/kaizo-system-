import unittest

from fastapi.testclient import TestClient

from main import app, ATHLETE_RECORDS, ASSESSMENT_RECORDS


class FEAT011MeasurementPersistenceTests(unittest.TestCase):
    def setUp(self):
        ATHLETE_RECORDS.clear()
        ASSESSMENT_RECORDS.clear()
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
