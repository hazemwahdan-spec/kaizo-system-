import unittest
from fastapi.testclient import TestClient
import main

class FEAT016StructuredProblemStatementTests(unittest.TestCase):
    def setUp(self):
        main.ATHLETE_RECORDS.clear()
        main.ASSESSMENT_RECORDS.clear()
        main.PROBLEM_STATEMENTS.clear()
        main.AUDIT_LOGS.clear()
        self.client=TestClient(main.app)

    def _assessment(self):
        a=self.client.post("/api/v1/athletes",json={"display_name":"FEAT016 Athlete"})
        self.assertEqual(a.status_code,201)
        aid=a.json()["athlete_id"]
        ass=self.client.post("/api/v1/assessments",json={
            "athlete_id":aid,"template_id":"ASSESSMENT-FEAT016",
            "measurements":{"entry_quality":4,"grip_strength_kg":15.0},
            "recorded_by":"coach-feat016"})
        self.assertEqual(ass.status_code,201)
        return a.json(),ass.json()

    def test_structured_problem_statement_persists_and_reads_back(self):
        athlete,assessment=self._assessment()
        r=self.client.post("/api/v1/problem-statements",json={
            "athlete_id":athlete["athlete_id"],
            "assessment_id":assessment["assessment_id"],
            "statement":"Athlete loses kuzushi before full entry under resistance.",
            "problem_type":"technical_execution",
            "impact":"Reduced successful entry rate.",
            "context":{"phase":"tsukuri","pressure":"live_resistance"},
            "structured_fields":{"observable":"loss_of_kuzushi","condition":"under_resistance"},
            "created_by":"coach-feat016"})
        self.assertEqual(r.status_code,201)
        p=r.json()
        self.assertEqual(p["status"],"OPEN")
        self.assertEqual(p["structured_fields"]["observable"],"loss_of_kuzushi")
        g=self.client.get("/api/v1/problem-statements/"+p["problem_id"])
        self.assertEqual(g.status_code,200)
        self.assertEqual(g.json(),p)

    def test_problem_statement_requires_existing_assessment_and_matching_athlete(self):
        athlete,assessment=self._assessment()
        missing=self.client.post("/api/v1/problem-statements",json={
            "athlete_id":athlete["athlete_id"],"assessment_id":"missing",
            "statement":"Problem","problem_type":"technical","created_by":"coach"})
        self.assertEqual(missing.status_code,404)
        other=self.client.post("/api/v1/athletes",json={"display_name":"Other"}).json()
        mismatch=self.client.post("/api/v1/problem-statements",json={
            "athlete_id":other["athlete_id"],"assessment_id":assessment["assessment_id"],
            "statement":"Problem","problem_type":"technical","created_by":"coach"})
        self.assertEqual(mismatch.status_code,400)

    def test_problem_statement_rejects_empty_required_fields(self):
        athlete,assessment=self._assessment()
        r=self.client.post("/api/v1/problem-statements",json={
            "athlete_id":athlete["athlete_id"],"assessment_id":assessment["assessment_id"],
            "statement":" ","problem_type":"technical","created_by":"coach"})
        self.assertEqual(r.status_code,400)

    def test_problem_statement_is_audited(self):
        athlete,assessment=self._assessment()
        r=self.client.post("/api/v1/problem-statements",json={
            "athlete_id":athlete["athlete_id"],"assessment_id":assessment["assessment_id"],
            "statement":"Problem with entry timing.","problem_type":"timing","created_by":"coach-feat016"})
        self.assertEqual(r.status_code,201)
        logs=self.client.get("/api/v1/audit/logs").json()["logs"]
        matches=[x for x in logs if x["action"]=="PROBLEM_STATEMENT_CREATED"]
        self.assertTrue(matches)
        self.assertEqual(matches[-1]["who"],"coach-feat016")
        self.assertEqual(matches[-1]["new_value"]["problem_type"],"timing")

if __name__=="__main__":
    unittest.main()
