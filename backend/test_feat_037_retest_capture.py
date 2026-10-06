import unittest
from retest_capture import RetestCapture, serialize

class TestFeat037(unittest.TestCase):
    def test_valid_and_guardrails(self):
        obj=RetestCapture("retest_id-sample", "athlete_id-sample", "kpi_values-sample", "method-sample", "captured_by-sample")
        out=serialize(obj)
        self.assertTrue(out["coach_final_authority"])
        self.assertFalse(out["execution_authorized"])

if __name__=="__main__": unittest.main()
