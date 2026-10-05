import unittest

from fastapi.testclient import TestClient
from main import app, DIGITAL_TWIN_STATE


class FEAT041DigitalTwinStateTests(unittest.TestCase):
    def setUp(self):
        DIGITAL_TWIN_STATE.clear()
        self.client = TestClient(app)

    def test_sync_creates_versioned_state_and_read_returns_it(self):
        response = self.client.post(
            "/api/v1/digital-twin/sync",
            json={
                "case_id": "CASE-FEAT041",
                "entity_id": "ATHLETE-041-PRIMARY",
                "state": {"readiness": "developing", "grip": 7},
                "source_event": "ASSESSMENT_RECORDED",
                "coach_final_authority": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "SYNCHRONIZED")
        self.assertEqual(payload["sync"]["previous_version"], 0)
        self.assertEqual(payload["sync"]["new_version"], 1)
        self.assertTrue(payload["coach_final_authority"])

        fetched = self.client.get("/api/v1/digital-twin/ATHLETE-041")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["digital_twin_state"]["version"], 1)
        self.assertEqual(
            fetched.json()["digital_twin_state"]["state"]["readiness"],
            "developing",
        )

    def test_sync_increments_version(self):
        base = {
            "case_id": "CASE-FEAT041",
            "entity_id": "ATHLETE-041-PRIMARY",
            "source_event": "ASSESSMENT_RECORDED",
            "coach_final_authority": True,
        }
        first = self.client.post("/api/v1/digital-twin/sync", json={**base, "state": {"score": 1}})
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            "/api/v1/digital-twin/sync",
            json={**base, "state": {"score": 2}, "expected_version": 1},
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["sync"]["new_version"], 2)

    def test_version_conflict_holds_and_does_not_mutate_state(self):
        base = {
            "case_id": "CASE-FEAT041",
            "entity_id": "ATHLETE-041-PRIMARY",
            "source_event": "ASSESSMENT_RECORDED",
            "coach_final_authority": True,
        }
        first = self.client.post("/api/v1/digital-twin/sync", json={**base, "state": {"score": 1}})
        self.assertEqual(first.status_code, 200)

        conflict = self.client.post(
            "/api/v1/digital-twin/sync",
            json={**base, "state": {"score": 99}, "expected_version": 0},
        )
        self.assertEqual(conflict.status_code, 200)
        self.assertEqual(conflict.json()["status"], "HOLD")
        self.assertEqual(conflict.json()["reason_code"], "DIGITAL_TWIN_VERSION_CONFLICT")

        fetched = self.client.get("/api/v1/digital-twin/ATHLETE-041")
        self.assertEqual(fetched.json()["digital_twin_state"]["state"]["score"], 1)
        self.assertEqual(fetched.json()["digital_twin_state"]["version"], 1)

    def test_coach_final_authority_is_required(self):
        response = self.client.post(
            "/api/v1/digital-twin/sync",
            json={
                "case_id": "CASE-FEAT041",
                "entity_id": "ATHLETE-041-PRIMARY",
                "state": {"score": 5},
                "source_event": "MANUAL_UPDATE",
                "coach_final_authority": False,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "HOLD")
        self.assertEqual(response.json()["reason_code"], "COACH_FINAL_AUTHORITY_REQUIRED")

    def test_sync_emits_audit_event(self):
        response = self.client.post(
            "/api/v1/digital-twin/sync",
            json={
                "case_id": "CASE-FEAT041",
                "entity_id": "ATHLETE-041-PRIMARY",
                "state": {"score": 8},
                "source_event": "ASSESSMENT_RECORDED",
                "coach_final_authority": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        audit = self.client.get("/api/v1/audit/logs")
        self.assertEqual(audit.status_code, 200)
        matches = [
            x for x in audit.json()["logs"]
            if x["action"] == "DIGITAL_TWIN_SYNCHRONIZED"
        ]
        self.assertTrue(matches)
        self.assertEqual(matches[-1]["new_value"]["entity_id"], "ATHLETE-041-PRIMARY")


if __name__ == "__main__":
    unittest.main()
