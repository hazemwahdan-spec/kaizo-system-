"""FEAT-051 public evidence boundary: fail closed until publisher auth is deployed.

Domain-level evidence persistence and linkage are exercised by the trusted fixtures
in the feature acceptance tests. This suite verifies that the legacy public API
cannot be used anonymously to read or forge evidence during containment.
"""
import unittest
from fastapi.testclient import TestClient
from main import app, EVIDENCE_RECORDS


class FEAT051EvidenceSpineTests(unittest.TestCase):
    def setUp(self):
        EVIDENCE_RECORDS.clear()
        self.client = TestClient(app)

    def test_anonymous_evidence_list_is_denied(self):
        response = self.client.get("/api/v1/evidence?subject_id=FEAT-051")
        self.assertEqual(response.status_code, 401)

    def test_anonymous_evidence_detail_is_denied(self):
        response = self.client.get("/api/v1/evidence/EVD-FEAT051-001")
        self.assertEqual(response.status_code, 401)

    def test_public_write_is_denied_and_cannot_forge_verified_by(self):
        response = self.client.post("/api/v1/evidence", json={
            "evidence_id": "EVD-FEAT051-001",
            "subject_type": "feature",
            "subject_id": "FEAT-051",
            "evidence_level": "E3",
            "status": "VERIFIED",
            "source_ref": "CI-RUN-1",
            "claim": "Evidence record is traceable",
            "observed_value": {"result": "PASS"},
            "verified_by": "forged-client-identity",
            "notes": "Acceptance evidence",
        })
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("EVD-FEAT051-001", EVIDENCE_RECORDS)


if __name__ == "__main__":
    unittest.main()
