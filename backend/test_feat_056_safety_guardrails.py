import unittest

from fastapi.testclient import TestClient
from main import app, AUDIT_LOGS


class FEAT056SafetyEvidenceGuardrailTests(unittest.TestCase):
    def setUp(self):
        AUDIT_LOGS.clear()
        self.client = TestClient(app)

    def _payload(self, **overrides):
        payload = {
            "action_id": "ACTION-FEAT056-001",
            "subject_id": "ATHLETE-FEAT056-001",
            "action_type": "TRAINING_PRESCRIPTION",
            "evidence_level": "E3",
            "evidence_status": "VERIFIED",
            "safety_constraints_met": True,
            "coach_final_authority": True,
            "rationale": "Acceptance case",
        }
        payload.update(overrides)
        return payload

    def test_verified_evidence_and_safety_constraints_allow_action(self):
        response = self.client.post("/api/v1/safety/evaluate", json=self._payload())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "SAFE_TO_PROCEED")
        self.assertFalse(body["decision_blocked"])

    def test_unverified_or_e0_evidence_holds(self):
        for overrides in (
            {"evidence_status": "UNVERIFIED"},
            {"evidence_level": "E0"},
        ):
            response = self.client.post("/api/v1/safety/evaluate", json=self._payload(**overrides))
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["status"], "HOLD")
            self.assertEqual(body["reason_code"], "EVIDENCE_QUALITY_INSUFFICIENT")
            self.assertTrue(body["decision_blocked"])

    def test_safety_constraint_violation_holds(self):
        response = self.client.post(
            "/api/v1/safety/evaluate",
            json=self._payload(safety_constraints_met=False),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "HOLD")
        self.assertEqual(body["reason_code"], "SAFETY_CONSTRAINT_VIOLATION")
        self.assertTrue(body["decision_blocked"])

    def test_coach_final_authority_is_required(self):
        response = self.client.post(
            "/api/v1/safety/evaluate",
            json=self._payload(coach_final_authority=False),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "HOLD")
        self.assertEqual(body["reason_code"], "COACH_FINAL_AUTHORITY_REQUIRED")
        self.assertTrue(body["decision_blocked"])

    def test_safety_evaluation_is_audited(self):
        response = self.client.post("/api/v1/safety/evaluate", json=self._payload())
        self.assertEqual(response.status_code, 200)
        matches = [
            item for item in AUDIT_LOGS
            if item["action"] == "SAFETY_EVALUATION_PASSED"
        ]
        self.assertTrue(matches)
        self.assertEqual(matches[-1]["who"], "ATHLETE-FEAT056-001")


if __name__ == "__main__":
    unittest.main()
