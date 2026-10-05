import unittest
from fastapi.testclient import TestClient

import main
import persistence


class FEAT020DiagnosisConfidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence.initialize()
        cls.client = TestClient(main.app)

    def setUp(self):
        athlete = self.client.post(
            "/api/v1/athletes",
            json={"display_name": "FEAT-020 Athlete", "metadata": {}},
        )
        self.assertEqual(athlete.status_code, 201)
        self.athlete_id = athlete.json()["athlete_id"]

        assessment = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": self.athlete_id,
                "template_id": "TPL-020",
                "measurements": {"entry_timing": "late"},
                "recorded_by": "coach-020",
            },
        )
        self.assertEqual(assessment.status_code, 201)
        self.assessment_id = assessment.json()["assessment_id"]

        problem = self.client.post(
            "/api/v1/problem-statements",
            json={
                "athlete_id": self.athlete_id,
                "assessment_id": self.assessment_id,
                "statement": "Late entry under resistance",
                "problem_type": "timing",
                "created_by": "coach-020",
            },
        )
        self.assertEqual(problem.status_code, 201)
        self.problem_id = problem.json()["problem_id"]

        evidence = self.client.post(
            "/api/v1/evidence",
            json={
                "evidence_id": "EVID-020-001",
                "subject_type": "assessment",
                "subject_id": self.assessment_id,
                "evidence_level": "E3",
                "status": "verified",
                "claim": "Late entry observed repeatedly",
                "observed_value": {"count": 4},
                "verified_by": "coach-020",
            },
        )
        self.assertEqual(evidence.status_code, 201)

    def _diagnosis(self, **overrides):
        payload = {
            "problem_id": self.problem_id,
            "evidence_ids": ["EVID-020-001"],
            "diagnosis": "Timing breakdown under pressure",
            "diagnosed_by": "coach-020",
        }
        payload.update(overrides)
        return self.client.post(
            f"/api/v1/problem-statements/{self.problem_id}/diagnosis",
            json=payload,
        )

    def test_default_state_is_explicitly_unresolved(self):
        response = self._diagnosis()
        self.assertEqual(response.status_code, 201)
        diagnosis = response.json()
        self.assertIsNone(diagnosis["confidence"])
        self.assertEqual(diagnosis["resolution_state"], "UNRESOLVED")

        read = self.client.get(
            f"/api/v1/problem-statements/{self.problem_id}/diagnosis"
        )
        self.assertEqual(read.status_code, 200)
        self.assertEqual(
            read.json()["diagnoses"][-1]["resolution_state"], "UNRESOLVED"
        )

    def test_confidence_and_resolved_state_persist(self):
        response = self._diagnosis(confidence="HIGH", resolution_state="RESOLVED")
        self.assertEqual(response.status_code, 201)
        diagnosis = response.json()
        self.assertEqual(diagnosis["confidence"], "HIGH")
        self.assertEqual(diagnosis["resolution_state"], "RESOLVED")

        read = self.client.get(
            f"/api/v1/problem-statements/{self.problem_id}/diagnosis"
        )
        self.assertEqual(read.status_code, 200)
        stored = read.json()["diagnoses"][-1]
        self.assertEqual(stored["confidence"], "HIGH")
        self.assertEqual(stored["resolution_state"], "RESOLVED")

    def test_invalid_confidence_and_resolution_state_are_blocked(self):
        bad_confidence = self._diagnosis(confidence="CERTAIN")
        self.assertEqual(bad_confidence.status_code, 400)

        bad_state = self._diagnosis(resolution_state="MAYBE")
        self.assertEqual(bad_state.status_code, 400)


if __name__ == "__main__":
    unittest.main()
