import unittest
from fastapi.testclient import TestClient
import main
import persistence


class FEAT021DecisionCandidateGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        persistence.initialize()
        cls.client = TestClient(main.app)

    def setUp(self):
        athlete = self.client.post("/api/v1/athletes", json={"display_name":"FEAT-021 Athlete","metadata":{}})
        self.assertEqual(athlete.status_code, 201)
        self.athlete_id = athlete.json()["athlete_id"]
        assessment = self.client.post("/api/v1/assessments", json={
            "athlete_id": self.athlete_id, "template_id":"TPL-021",
            "measurements":{"entry_timing":"late"}, "recorded_by":"coach-021"})
        self.assertEqual(assessment.status_code, 201)
        self.assessment_id = assessment.json()["assessment_id"]
        problem = self.client.post("/api/v1/problem-statements", json={
            "athlete_id":self.athlete_id, "assessment_id":self.assessment_id,
            "statement":"Late entry under resistance","problem_type":"timing","created_by":"coach-021"})
        self.assertEqual(problem.status_code, 201)
        evidence = self.client.post("/api/v1/evidence", json={
            "evidence_id":"EVID-021-001","subject_type":"assessment",
            "subject_id":self.assessment_id,"evidence_level":"E3","status":"verified",
            "claim":"Late entry observed","observed_value":{"count":4},"verified_by":"coach-021"})
        self.assertEqual(evidence.status_code, 201)
        diagnosis = self.client.post(
            f"/api/v1/problem-statements/{problem.json()['problem_id']}/diagnosis",
            json={"problem_id":problem.json()["problem_id"],"evidence_ids":["EVID-021-001"],
                  "diagnosis":"Timing breakdown under pressure","confidence":"HIGH","diagnosed_by":"coach-021"})
        self.assertEqual(diagnosis.status_code, 201)
        self.diagnosis = diagnosis.json()

    def test_generates_reviewable_candidates_with_lineage(self):
        r=self.client.post(
            f"/api/v1/diagnoses/{self.diagnosis['diagnosis_id']}/decision-candidates",
            json={"diagnosis_id":self.diagnosis["diagnosis_id"],"requested_by":"coach-021"})
        self.assertEqual(r.status_code,201)
        body=r.json()
        self.assertEqual(body["status"],"CANDIDATES_GENERATED")
        self.assertTrue(body["coach_review_required"])
        self.assertGreaterEqual(len(body["candidates"]),2)
        for candidate in body["candidates"]:
            self.assertEqual(candidate["diagnosis_id"],self.diagnosis["diagnosis_id"])
            self.assertEqual(candidate["problem_id"],self.diagnosis["problem_id"])
            self.assertEqual(candidate["athlete_id"],self.athlete_id)
            self.assertEqual(candidate["status"],"PENDING_COACH_REVIEW")

    def test_candidates_persist_and_read_back(self):
        r=self.client.post(
            f"/api/v1/diagnoses/{self.diagnosis['diagnosis_id']}/decision-candidates",
            json={"diagnosis_id":self.diagnosis["diagnosis_id"],"requested_by":"coach-021"})
        self.assertEqual(r.status_code,201)
        read=self.client.get(
            f"/api/v1/diagnoses/{self.diagnosis['diagnosis_id']}/decision-candidates")
        self.assertEqual(read.status_code,200)
        self.assertEqual(len(read.json()["candidates"]),len(r.json()["candidates"]))

    def test_missing_diagnosis_and_mismatch_are_blocked(self):
        missing=self.client.post(
            "/api/v1/diagnoses/missing/decision-candidates",
            json={"diagnosis_id":"missing","requested_by":"coach-021"})
        self.assertEqual(missing.status_code,404)
        mismatch=self.client.post(
            f"/api/v1/diagnoses/{self.diagnosis['diagnosis_id']}/decision-candidates",
            json={"diagnosis_id":"other","requested_by":"coach-021"})
        self.assertEqual(mismatch.status_code,400)

    def test_generation_is_audited(self):
        r=self.client.post(
            f"/api/v1/diagnoses/{self.diagnosis['diagnosis_id']}/decision-candidates",
            json={"diagnosis_id":self.diagnosis["diagnosis_id"],"requested_by":"coach-021"})
        self.assertEqual(r.status_code,201)
        logs=self.client.get("/api/v1/audit/logs").json()["logs"]
        self.assertTrue(any(x["action"]=="DECISION_CANDIDATES_GENERATED" for x in logs))


if __name__=="__main__":
    unittest.main()
