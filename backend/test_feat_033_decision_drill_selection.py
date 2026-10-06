import unittest
from decision_drill_selection import DecisionDrillSelection, serialize

class TestFeat033(unittest.TestCase):
    def test_valid_and_guardrails(self):
        obj=DecisionDrillSelection("sample", "sample", "sample", "sample")
        out=serialize(obj)
        self.assertTrue(out["coach_final_authority"])
        self.assertFalse(out["execution_authorized"])

if __name__=="__main__": unittest.main()
