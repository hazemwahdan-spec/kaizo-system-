import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
import main
import persistence
from main import app, DIGITAL_TWIN_STATE
from phase4_core_resource_authorization import require_core_actor
from productization.identity import Principal


class CoreAuthTestOverrides:
    def _install_auth_test_overrides(self):
        self.principal = Principal(
            actor_id="unit-test-coach", role="coach", tenant_id="unit-test-academy",
            resource_owner_id=None, verified=True, source="test_override",
        )
        app.dependency_overrides[require_core_actor] = lambda: self.principal
        self._authorization_patches = [
            patch("main.bind_new_resource"),
            patch("main.assert_resource_tenant"),
            patch("main.assert_assessment_tenant"),
        ]
        for item in self._authorization_patches:
            item.start()
        self.addCleanup(self._cleanup_auth_test_overrides)

    def _cleanup_auth_test_overrides(self):
        app.dependency_overrides.pop(require_core_actor, None)
        for item in reversed(self._authorization_patches):
            item.stop()


class FEAT041DigitalTwinStateTests(CoreAuthTestOverrides, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence.initialize()
        if persistence.is_postgres_enabled():
            for migration in (
                Path("migrations/0001_phase4_identity_consent.sql"),
                Path("migrations/20261012_phase4_identity_consent_canonical.sql"),
            ):
                with persistence.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(migration.read_text())
                    conn.commit()

    def setUp(self):
        self._install_auth_test_overrides()
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

        fetched = self.client.get("/api/v1/digital-twin/ATHLETE-041-PRIMARY")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["digital_twin_state"]["version"], 1)
        self.assertEqual(
            fetched.json()["digital_twin_state"]["state"]["readiness"],
            "developing",
        )

    def test_sync_increments_version(self):
        base = {
            "case_id": "CASE-FEAT041",
            "entity_id": "ATHLETE-041-VERSION",
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
            "entity_id": "ATHLETE-041-CONFLICT",
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

        fetched = self.client.get("/api/v1/digital-twin/ATHLETE-041-CONFLICT")
        self.assertEqual(fetched.json()["digital_twin_state"]["state"]["score"], 1)
        self.assertEqual(fetched.json()["digital_twin_state"]["version"], 1)

    def test_coach_final_authority_is_required(self):
        response = self.client.post(
            "/api/v1/digital-twin/sync",
            json={
                "case_id": "CASE-FEAT041",
                "entity_id": "ATHLETE-041-AUTH",
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
                "entity_id": "ATHLETE-041-AUDIT",
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
        self.assertEqual(matches[-1]["new_value"]["entity_id"], "ATHLETE-041-AUDIT")


if __name__ == "__main__":
    unittest.main()
