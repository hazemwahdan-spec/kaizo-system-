import unittest
from fastapi.testclient import TestClient
from main import app, EVIDENCE_RECORDS

class FEAT051EvidenceSpineTests(unittest.TestCase):
    def setUp(self):
        EVIDENCE_RECORDS.clear()
        self.client = TestClient(app)

    def test_record_and_read_evidence(self):
        created = self.client.post("/api/v1/evidence", json={
            "evidence_id": "EVD-FEAT051-001",
            "subject_type": "feature",
            "subject_id": "FEAT-051",
            "evidence_level": "E3",
            "status": "VERIFIED",
            "source_ref": "CI-RUN-1",
            "claim": "Evidence record is traceable",
            "observed_value": {"result": "PASS"},
            "verified_by": "coach-001",
            "notes": "Acceptance evidence"
        })
        self.assertEqual(created.status_code, 201)
        record = created.json()
        self.assertEqual(record["evidence_level"], "E3")
        self.assertTrue(record["verified_at"])

        fetched = self.client.get("/api/v1/evidence/EVD-FEAT051-001")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json(), record)

        listed = self.client.get("/api/v1/evidence?subject_id=FEAT-051")
        self.assertEqual(listed.status_code, 200)
        self.assertGreaterEqual(listed.json()["total_evidence"], 1)
        ids = {item["evidence_id"] for item in listed.json()["records"]}
        self.assertIn("EVD-FEAT051-001", ids)

    def test_invalid_evidence_level_is_blocked(self):
        response = self.client.post("/api/v1/evidence", json={
            "evidence_id": "EVD-BAD",
            "subject_type": "feature",
            "subject_id": "FEAT-051",
            "evidence_level": "E9",
            "status": "VERIFIED",
            "claim": "bad",
            "verified_by": "coach-001"
        })
        self.assertEqual(response.status_code, 400)

    def test_evidence_event_is_audited(self):
        self.client.post("/api/v1/evidence", json={
            "evidence_id": "EVD-AUDIT",
            "subject_type": "feature",
            "subject_id": "FEAT-051",
            "evidence_level": "E2",
            "status": "VERIFIED",
            "claim": "audited evidence",
            "verified_by": "coach-002"
        })
        audit = self.client.get("/api/v1/audit/logs")
        self.assertEqual(audit.status_code, 200)
        matches = [x for x in audit.json()["logs"] if x["action"] == "EVIDENCE_RECORDED"]
        self.assertTrue(matches)
        self.assertEqual(matches[-1]["who"], "coach-002")

if __name__ == "__main__":
    unittest.main()
