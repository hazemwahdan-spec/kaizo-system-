import unittest
from training_response_capture import TrainingResponse, serialize

class TestFeat036(unittest.TestCase):
    def test_valid_and_guardrails(self):
        obj=TrainingResponse("response_id-sample", "session_id-sample", "athlete_id-sample", "response-sample", "kpi_values-sample", "captured_by-sample")
        out=serialize(obj)
        self.assertTrue(out["coach_final_authority"])
        self.assertFalse(out["execution_authorized"])

if __name__=="__main__": unittest.main()
