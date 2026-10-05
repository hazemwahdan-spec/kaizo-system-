import unittest
from fastapi.testclient import TestClient
import main, persistence

class FEAT022Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence.initialize()
        cls.c=TestClient(main.app)

    def setUp(self):
        a=self.c.post("/api/v1/athletes",json={"display_name":"FEAT022","metadata":{}}); self.assertEqual(a.status_code,201)
        self.aid=a.json()["athlete_id"]
        s=self.c.post("/api/v1/assessments",json={"athlete_id":self.aid,"template_id":"T22","measurements":{"x":1},"recorded_by":"coach"}); self.assertEqual(s.status_code,201)
        self.sid=s.json()["assessment_id"]
        p=self.c.post("/api/v1/problem-statements",json={"athlete_id":self.aid,"assessment_id":self.sid,"statement":"problem","problem_type":"timing","created_by":"coach"}); self.assertEqual(p.status_code,201)
        self.pid=p.json()["problem_id"]
        e=self.c.post("/api/v1/evidence",json={"evidence_id":"E22","subject_type":"assessment","subject_id":self.sid,"evidence_level":"E3","status":"verified","claim":"observed","observed_value":{"n":1},"verified_by":"coach"}); self.assertEqual(e.status_code,201)
        d=self.c.post(f"/api/v1/problem-statements/{self.pid}/diagnosis",json={"problem_id":self.pid,"evidence_ids":["E22"],"diagnosis":"diagnosis","confidence":"HIGH","diagnosed_by":"coach"}); self.assertEqual(d.status_code,201)
        g=self.c.post(f"/api/v1/diagnoses/{d.json()['diagnosis_id']}/decision-candidates",json={"diagnosis_id":d.json()["diagnosis_id"],"requested_by":"coach"}); self.assertEqual(g.status_code,201)
        self.cid=g.json()["candidates"][0]["candidate_id"]

    def test_record_and_read(self):
        r=self.c.post(f"/api/v1/decision-candidates/{self.cid}/rationale",json={"candidate_id":self.cid,"rationale":"Evidence supports this candidate.","evidence_ids":["E22"],"recorded_by":"coach"})
        self.assertEqual(r.status_code,201); self.assertTrue(r.json()["coach_review_required"])
        q=self.c.get(f"/api/v1/decision-candidates/{self.cid}/rationale")
        self.assertEqual(q.status_code,200); self.assertEqual(q.json()["rationales"][0]["evidence_ids"],["E22"])

    def test_missing_candidate_or_evidence_blocked(self):
        r=self.c.post("/api/v1/decision-candidates/missing/rationale",json={"candidate_id":"missing","rationale":"x","evidence_ids":["E22"],"recorded_by":"coach"})
        self.assertEqual(r.status_code,404)
        r=self.c.post(f"/api/v1/decision-candidates/{self.cid}/rationale",json={"candidate_id":self.cid,"rationale":"x","evidence_ids":["NO-EVID"],"recorded_by":"coach"})
        self.assertEqual(r.status_code,404)

    def test_audit(self):
        r=self.c.post(f"/api/v1/decision-candidates/{self.cid}/rationale",json={"candidate_id":self.cid,"rationale":"Audit rationale","evidence_ids":["E22"],"recorded_by":"coach"})
        self.assertEqual(r.status_code,201)
        logs=self.c.get("/api/v1/audit/logs").json()["logs"]
        self.assertTrue(any(x["action"]=="DECISION_RATIONALE_RECORDED" for x in logs))

if __name__=="__main__":
    unittest.main()
