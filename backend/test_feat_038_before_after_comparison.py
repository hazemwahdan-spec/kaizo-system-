import unittest
from before_after_comparison import BeforeAfterComparison, serialize

class TestFeat038(unittest.TestCase):
    def test_valid_and_guardrails(self):
        obj=BeforeAfterComparison("comparison_id-sample", "baseline_id-sample", "retest_id-sample", "findings-sample", "compared_by-sample")
        out=serialize(obj)
        self.assertTrue(out["coach_final_authority"])
        self.assertFalse(out["execution_authorized"])

if __name__=="__main__": unittest.main()
