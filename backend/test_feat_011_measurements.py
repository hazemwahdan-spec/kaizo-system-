import unittest

from fastapi.testclient import TestClient

from main import app, ATHLETE_RECORDS, ASSESSMENT_RECORDS, AUDIT_LOGS


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


class FEAT046AuditSpineTests(unittest.TestCase):
    def setUp(self):
        ATHLETE_RECORDS.clear()
        ASSESSMENT_RECORDS.clear()
        AUDIT_LOGS.clear()
        self.client = TestClient(app)

    def test_assessment_action_is_written_to_audit_spine(self):
        athlete = self.client.post(
            "/api/v1/athletes", json={"display_name": "Audit Athlete"}
        )
        self.assertEqual(athlete.status_code, 201)

        created = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": athlete.json()["athlete_id"],
                "template_id": "AUDIT-SPINE",
                "measurements": {"score": 7},
                "recorded_by": "coach-audit",
            },
        )
        self.assertEqual(created.status_code, 201)

        # This verifies only the in-process event boundary; it is not evidence
        # of durable or tenant-scoped production audit access.
        matching = [
            entry for entry in AUDIT_LOGS
            if entry["action"] == "ASSESSMENT_RECORDED"
        ]
        self.assertTrue(matching)
        self.assertEqual(matching[-1]["who"], "coach-audit")
        self.assertEqual(
            matching[-1]["new_value"]["athlete_id"],
            athlete.json()["athlete_id"],
        )
        self.assertEqual(
            matching[-1]["why"],
            "Assessment measurements persisted with explicit athlete ownership and timestamp.",
        )

    def test_legacy_audit_read_endpoint_fails_closed_without_verified_authorization(self):
        response = self.client.get("/api/v1/audit/logs")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Audit log access is temporarily disabled pending verified identity and tenant authorization.",
        )
