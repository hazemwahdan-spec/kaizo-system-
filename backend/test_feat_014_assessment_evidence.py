import unittest
from fastapi.testclient import TestClient

import main


class FEAT014AssessmentEvidenceAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.athlete_id = self.client.post(
            "/api/v1/athletes",
            json={"display_name": "FEAT-014 Athlete"},
        ).json()["athlete_id"]
        self.assessment_id = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": self.athlete_id,
                "template_id": "TEMPLATE-FEAT014",
                "measurements": {"grip_strength": 21.5},
                "recorded_by": "coach-feat014",
            },
        ).json()["assessment_id"]

    def _record_evidence(self, evidence_id, subject_id=None):
        return self.client.post(
            "/api/v1/evidence",
            json={
                "evidence_id": evidence_id,
                "subject_type": "assessment",
                "subject_id": subject_id or self.assessment_id,
                "evidence_level": "E3",
                "status": "VERIFIED",
                "source_ref": "assessment://FEAT-014",
                "claim": "Assessment measurement is supported by attached evidence.",
                "observed_value": {"grip_strength": 21.5},
                "verified_by": "coach-feat014",
            },
        )

    def test_attach_evidence_to_assessment_and_read_back(self):
        evidence = self._record_evidence("EVIDENCE-FEAT014-001")
        self.assertEqual(evidence.status_code, 201)

        response = self.client.post(
            f"/api/v1/assessments/{self.assessment_id}/evidence",
            json={
                "assessment_id": self.assessment_id,
                "evidence_id": "EVIDENCE-FEAT014-001",
                "attached_by": "coach-feat014",
            },
        )
        self.assertEqual(response.status_code, 201)
        attachment = response.json()
        self.assertEqual(attachment["assessment_id"], self.assessment_id)
        self.assertEqual(attachment["evidence_id"], "EVIDENCE-FEAT014-001")

        readback = self.client.get(f"/api/v1/assessments/{self.assessment_id}/evidence")
        self.assertEqual(readback.status_code, 200)
        self.assertIn(
            "EVIDENCE-FEAT014-001",
            [item["evidence_id"] for item in readback.json()["attachments"]],
        )

    def test_attachment_requires_existing_assessment_and_evidence(self):
        missing_assessment = self.client.post(
            "/api/v1/assessments/missing-assessment/evidence",
            json={
                "assessment_id": "missing-assessment",
                "evidence_id": "missing-evidence",
                "attached_by": "coach-feat014",
            },
        )
        self.assertEqual(missing_assessment.status_code, 404)

        missing_evidence = self.client.post(
            f"/api/v1/assessments/{self.assessment_id}/evidence",
            json={
                "assessment_id": self.assessment_id,
                "evidence_id": "missing-evidence",
                "attached_by": "coach-feat014",
            },
        )
        self.assertEqual(missing_evidence.status_code, 404)

    def test_attachment_rejects_evidence_scoped_to_another_assessment(self):
        other_assessment = self.client.post(
            "/api/v1/assessments",
            json={
                "athlete_id": self.athlete_id,
                "template_id": "TEMPLATE-FEAT014-OTHER",
                "measurements": {"grip_strength": 20.0},
                "recorded_by": "coach-feat014",
            },
        ).json()["assessment_id"]
        self.assertEqual(
            self._record_evidence("EVIDENCE-FEAT014-002", other_assessment).status_code,
            201,
        )
        response = self.client.post(
            f"/api/v1/assessments/{self.assessment_id}/evidence",
            json={
                "assessment_id": self.assessment_id,
                "evidence_id": "EVIDENCE-FEAT014-002",
                "attached_by": "coach-feat014",
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_attachment_is_audited(self):
        self._record_evidence("EVIDENCE-FEAT014-003")
        response = self.client.post(
            f"/api/v1/assessments/{self.assessment_id}/evidence",
            json={
                "assessment_id": self.assessment_id,
                "evidence_id": "EVIDENCE-FEAT014-003",
                "attached_by": "coach-feat014",
            },
        )
        self.assertEqual(response.status_code, 201)
        logs = self.client.get("/api/v1/audit/logs").json()["logs"]
        actions = [entry for entry in logs if entry["action"] == "ASSESSMENT_EVIDENCE_ATTACHED"]
        self.assertTrue(actions)
        self.assertEqual(actions[-1]["who"], "coach-feat014")
        self.assertEqual(actions[-1]["new_value"]["assessment_id"], self.assessment_id)


if __name__ == "__main__":
    unittest.main()
