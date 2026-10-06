import unittest
from drill_prescription import DrillPrescription, serialize

class TestFeat034(unittest.TestCase):
    def test_valid_and_guardrails(self):
        obj=DrillPrescription("sample", "sample", "sample", "sample", "sample", "sample")
        out=serialize(obj)
        self.assertTrue(out["coach_final_authority"])
        self.assertFalse(out["execution_authorized"])

if __name__=="__main__": unittest.main()
