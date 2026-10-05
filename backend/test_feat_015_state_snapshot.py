import unittest
from fastapi.testclient import TestClient
import main

class FEAT015BaselineCurrentStateSnapshotTests(unittest.TestCase):
    def setUp(self):
        main.ATHLETE_RECORDS.clear()
        main.ASSESSMENT_RECORDS.clear()
        main.KPI_DEFINITIONS.clear()
        main.KPI_CAPTURES.clear()
        main.STATE_SNAPSHOTS.clear()
        main.AUDIT_LOGS.clear()
        self.client=TestClient(main.app)

    def _fixtures(self):
        athlete=self.client.post("/api/v1/athletes",json={"display_name":"FEAT015 Athlete"})
        self.assertEqual(athlete.status_code,201)
        aid=athlete.json()["athlete_id"]
        assessment=self.client.post("/api/v1/assessments",json={"athlete_id":aid,"template_id":"ASSESSMENT-FEAT015","measurements":{"entry_quality":7,"grip_strength_kg":18.5},"recorded_by":"coach-feat015"})
        self.assertEqual(assessment.status_code,201)
        kpi=self.client.post("/api/v1/kpis",json={"kpi_id":"KPI-FEAT015","name":"Grip strength","metric_name":"grip_strength","unit":"kg","target":25.0,"direction":"higher_is_better","defined_by":"coach-feat015"})
        self.assertEqual(kpi.status_code,201)
        capture=self.client.post("/api/v1/kpis/captures",json={"athlete_id":aid,"kpi_id":"KPI-FEAT015","value":18.5,"captured_by":"coach-feat015","assessment_id":assessment.json()["assessment_id"]})
        self.assertEqual(capture.status_code,201)
        return athlete.json(),assessment.json(),capture.json()

    def test_baseline_snapshot_materializes_assessment_and_kpis(self):
        athlete,assessment,capture=self._fixtures()
        r=self.client.post("/api/v1/state-snapshots",json={"athlete_id":athlete["athlete_id"],"assessment_id":assessment["assessment_id"],"snapshot_type":"baseline","kpi_capture_ids":[capture["capture_id"]],"captured_by":"coach-feat015"})
        self.assertEqual(r.status_code,201)
        s=r.json()
        self.assertEqual(s["snapshot_type"],"baseline")
        self.assertEqual(s["athlete_id"],athlete["athlete_id"])
        self.assertEqual(s["assessment_id"],assessment["assessment_id"])
        self.assertEqual(s["measurements"]["entry_quality"],7)
        self.assertEqual(s["kpis"][0]["value"],18.5)

    def test_current_state_snapshot_readback(self):
        athlete,assessment,capture=self._fixtures()
        r=self.client.post("/api/v1/state-snapshots",json={"athlete_id":athlete["athlete_id"],"assessment_id":assessment["assessment_id"],"snapshot_type":"current_state","kpi_capture_ids":[capture["capture_id"]],"captured_by":"coach-feat015"})
        self.assertEqual(r.status_code,201)
        s=r.json()
        g=self.client.get("/api/v1/state-snapshots/"+s["snapshot_id"])
        self.assertEqual(g.status_code,200)
        self.assertEqual(g.json(),s)

    def test_snapshot_rejects_missing_and_cross_athlete_dependencies(self):
        athlete,assessment,capture=self._fixtures()
        missing=self.client.post("/api/v1/state-snapshots",json={"athlete_id":athlete["athlete_id"],"assessment_id":assessment["assessment_id"],"snapshot_type":"baseline","kpi_capture_ids":["missing"],"captured_by":"coach-feat015"})
        self.assertEqual(missing.status_code,404)
        other=self.client.post("/api/v1/athletes",json={"display_name":"Other"}).json()
        mismatch=self.client.post("/api/v1/state-snapshots",json={"athlete_id":other["athlete_id"],"assessment_id":assessment["assessment_id"],"snapshot_type":"current_state","kpi_capture_ids":[capture["capture_id"]],"captured_by":"coach-feat015"})
        self.assertEqual(mismatch.status_code,400)

    def test_snapshot_is_audited(self):
        athlete,assessment,capture=self._fixtures()
        r=self.client.post("/api/v1/state-snapshots",json={"athlete_id":athlete["athlete_id"],"assessment_id":assessment["assessment_id"],"snapshot_type":"baseline","kpi_capture_ids":[capture["capture_id"]],"captured_by":"coach-feat015"})
        self.assertEqual(r.status_code,201)
        logs=self.client.get("/api/v1/audit/logs").json()["logs"]
        matches=[x for x in logs if x["action"]=="ATHLETE_STATE_SNAPSHOT_CREATED"]
        self.assertTrue(matches)
        self.assertEqual(matches[-1]["who"],"coach-feat015")

if __name__=="__main__":
    unittest.main()
