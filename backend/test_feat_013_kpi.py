import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

import main
from phase4_core_resource_authorization import require_core_actor
from productization.identity import Principal


class FEAT013KPIAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.principal = Principal(
            actor_id="unit-test-coach", role="coach", tenant_id="unit-test-academy",
            resource_owner_id=None, verified=True, source="test_override",
        )
        main.app.dependency_overrides[require_core_actor] = lambda: self.principal
        self._binding_patches = [
            patch("main.bind_new_resource"),
            patch("main.assert_resource_tenant"),
            patch("main.assert_assessment_tenant"),
            patch("main.assert_minor_consent"),
            patch("main.assert_minor_consent"),
        ]
        for item in self._binding_patches:
            item.start()
        self.addCleanup(self._cleanup_authorization_patches)
        self.client = TestClient(main.app)
        self.kpi_id = "KPI-FEAT013-001"
        self.athlete_id = self.client.post(
            "/api/v1/athletes", json={"display_name": "FEAT-013 Athlete"}
        ).json()["athlete_id"]

    def _cleanup_authorization_patches(self):
        main.app.dependency_overrides.pop(require_core_actor, None)
        for item in reversed(self._binding_patches):
            item.stop()

    def test_define_kpi_preserves_semantics_and_is_readable(self):
        response = self.client.post("/api/v1/kpis", json={
            "kpi_id": self.kpi_id, "name": "Grip strength", "metric_name": "grip_strength",
            "unit": "kg", "target": 25.0, "direction": "higher_is_better", "defined_by": "coach-feat013",
        })
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["kpi_id"], self.kpi_id)
        self.assertEqual(body["metric_name"], "grip_strength")
        self.assertEqual(body["unit"], "kg")
        self.assertEqual(body["target"], 25.0)
        self.assertEqual(self.client.get(f"/api/v1/kpis/{self.kpi_id}").json()["name"], "Grip strength")

    def test_capture_kpi_requires_existing_athlete_and_definition(self):
        missing_athlete = self.client.post("/api/v1/kpis/captures", json={
            "athlete_id": "missing-athlete", "kpi_id": self.kpi_id, "value": 21.0, "captured_by": "coach-feat013"
        })
        self.assertEqual(missing_athlete.status_code, 404)
        self.client.post("/api/v1/kpis", json={
            "kpi_id": self.kpi_id, "name": "Grip strength", "metric_name": "grip_strength", "unit": "kg", "defined_by": "coach-feat013"
        })
        missing_kpi = self.client.post("/api/v1/kpis/captures", json={
            "athlete_id": self.athlete_id, "kpi_id": "missing-kpi", "value": 21.0, "captured_by": "coach-feat013"
        })
        self.assertEqual(missing_kpi.status_code, 404)

    def test_capture_kpi_preserves_value_ownership_and_audit(self):
        self.client.post("/api/v1/kpis", json={
            "kpi_id": self.kpi_id, "name": "Grip strength", "metric_name": "grip_strength", "unit": "kg", "defined_by": "coach-feat013"
        })
        response = self.client.post("/api/v1/kpis/captures", json={
            "athlete_id": self.athlete_id, "kpi_id": self.kpi_id, "value": 21.5, "captured_by": "coach-feat013"
        })
        self.assertEqual(response.status_code, 201)
        capture = response.json()
        self.assertEqual(capture["athlete_id"], self.athlete_id)
        self.assertEqual(capture["kpi_id"], self.kpi_id)
        self.assertEqual(capture["value"], 21.5)
        readback = self.client.get(f"/api/v1/kpis/captures/{capture['capture_id']}")
        self.assertEqual(readback.status_code, 200)
        logs = self.client.get("/api/v1/audit/logs").json()["logs"]
        actions = [entry for entry in logs if entry["action"] == "KPI_CAPTURED"]
        self.assertTrue(actions)
        self.assertEqual(actions[-1]["who"], "coach-feat013")
        self.assertEqual(actions[-1]["new_value"]["athlete_id"], self.athlete_id)

    def test_invalid_kpi_direction_is_rejected(self):
        response = self.client.post("/api/v1/kpis", json={
            "kpi_id": self.kpi_id, "name": "Grip strength", "metric_name": "grip_strength",
            "unit": "kg", "direction": "invalid", "defined_by": "coach-feat013"
        })
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
