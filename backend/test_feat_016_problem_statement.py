import unittest
from fastapi.testclient import TestClient
import main
import persistence

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



class FEAT017ProblemLibrarySelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence.initialize()
        item = {"id": "PRB-017-001", "domain": "Problem", "title": "Grip entry timing problem", "status": "Published"}
        main.KNOWLEDGE_REPOSITORY["PRB-017-001"] = item
        persistence.upsert_knowledge("PRB-017-001", item, "2026-10-05T00:00:00")
        cls.client = TestClient(main.app)

    def setUp(self):
        athlete = self.client.post("/api/v1/athletes", json={"display_name": "FEAT-017 Athlete", "metadata": {}})
        self.athlete_id = athlete.json()["athlete_id"]
        assessment = self.client.post("/api/v1/assessments", json={"athlete_id": self.athlete_id, "template_id": "TPL-017", "measurements": {"entry_timing": "late"}, "recorded_by": "coach-017"})
        self.assessment_id = assessment.json()["assessment_id"]

    def test_library_lists_problem_entries(self):
        response = self.client.get("/api/v1/problem-library")
        self.assertEqual(response.status_code, 200)
        self.assertIn("PRB-017-001", [item["id"] for item in response.json()["items"]])

    def test_selection_persists_and_reads_back(self):
        response = self.client.post("/api/v1/problem-library/selections", json={"athlete_id": self.athlete_id, "assessment_id": self.assessment_id, "library_item_id": "PRB-017-001", "selected_by": "coach-017"})
        self.assertEqual(response.status_code, 201)
        selection = response.json()
        read = self.client.get(f"/api/v1/problem-library/selections/{selection['selection_id']}")
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.json(), selection)

    def test_invalid_library_item_and_cross_owner_are_blocked(self):
        unknown = self.client.post("/api/v1/problem-library/selections", json={"athlete_id": self.athlete_id, "assessment_id": self.assessment_id, "library_item_id": "PRB-DOES-NOT-EXIST", "selected_by": "coach-017"})
        self.assertEqual(unknown.status_code, 404)
        main.KNOWLEDGE_REPOSITORY["TEC-017-001"] = {"id": "TEC-017-001", "domain": "Technique", "title": "Technique item"}
        non_problem = self.client.post("/api/v1/problem-library/selections", json={"athlete_id": self.athlete_id, "assessment_id": self.assessment_id, "library_item_id": "TEC-017-001", "selected_by": "coach-017"})
        self.assertEqual(non_problem.status_code, 400)
        other = self.client.post("/api/v1/athletes", json={"display_name": "Other Athlete", "metadata": {}})
        cross = self.client.post("/api/v1/problem-library/selections", json={"athlete_id": other.json()["athlete_id"], "assessment_id": self.assessment_id, "library_item_id": "PRB-017-001", "selected_by": "coach-017"})
        self.assertEqual(cross.status_code, 400)

    def test_selection_is_audited(self):
        response = self.client.post("/api/v1/problem-library/selections", json={"athlete_id": self.athlete_id, "assessment_id": self.assessment_id, "library_item_id": "PRB-017-001", "selected_by": "coach-017"})
        self.assertEqual(response.status_code, 201)
        logs = self.client.get("/api/v1/audit/logs")
        self.assertTrue(any(item["action"] == "PROBLEM_LIBRARY_SELECTED" and item["new_value"]["library_item_id"] == "PRB-017-001" for item in logs.json()["logs"]))



class FEAT018CauseContextFramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence.initialize()
        cls.client = TestClient(main.app)

    def setUp(self):
        a = self.client.post("/api/v1/athletes", json={"display_name":"FEAT-018","metadata":{}})
        self.assertEqual(a.status_code, 201)
        self.athlete_id = a.json()["athlete_id"]
        a = self.client.post("/api/v1/assessments", json={"athlete_id":self.athlete_id,"template_id":"TPL-018","measurements":{"grip":"late"},"recorded_by":"coach-018"})
        self.assertEqual(a.status_code, 201)
        self.assessment_id = a.json()["assessment_id"]
        p = self.client.post("/api/v1/problem-statements", json={"athlete_id":self.athlete_id,"assessment_id":self.assessment_id,"statement":"Late grip","problem_type":"timing","created_by":"coach-018"})
        self.assertEqual(p.status_code, 201)
        self.problem_id = p.json()["problem_id"]

    def test_framing_persists_and_reads_back(self):
        r=self.client.post(f"/api/v1/problem-statements/{self.problem_id}/cause-context",json={"problem_id":self.problem_id,"cause":"Late grip acquisition","context":{"phase":"kumi-kata"},"contributing_factors":["distance","timing"],"framed_by":"coach-018"})
        self.assertEqual(r.status_code,201)
        read=self.client.get(f"/api/v1/problem-statements/{self.problem_id}/cause-context")
        self.assertEqual(read.status_code,200)
        self.assertIn(r.json(),read.json()["framings"])

    def test_missing_problem_and_invalid_payload_are_blocked(self):
        r=self.client.post("/api/v1/problem-statements/missing/cause-context",json={"problem_id":"missing","cause":"x","framed_by":"coach-018"})
        self.assertEqual(r.status_code,404)
        r=self.client.post(f"/api/v1/problem-statements/{self.problem_id}/cause-context",json={"problem_id":self.problem_id,"cause":" ","framed_by":"coach-018"})
        self.assertEqual(r.status_code,400)

    def test_mismatch_and_audit(self):
        r=self.client.post(f"/api/v1/problem-statements/{self.problem_id}/cause-context",json={"problem_id":"other","cause":"x","framed_by":"coach-018"})
        self.assertEqual(r.status_code,400)
        r=self.client.post(f"/api/v1/problem-statements/{self.problem_id}/cause-context",json={"problem_id":self.problem_id,"cause":"Late grip","framed_by":"coach-018"})
        self.assertEqual(r.status_code,201)
        logs=self.client.get("/api/v1/audit/logs").json()["logs"]
        self.assertTrue(any(x["action"]=="PROBLEM_CAUSE_CONTEXT_FRAMED" and x["new_value"]["problem_id"]==self.problem_id for x in logs))


