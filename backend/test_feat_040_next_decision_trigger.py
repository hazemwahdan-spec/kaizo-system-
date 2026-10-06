import unittest
from next_decision_trigger import NextDecisionTrigger,serialize
class TestFeat040(unittest.TestCase):
 def test_valid(self):
  o=NextDecisionTrigger("trigger_id","athlete_id","state_id","reason","triggered_by"); d=serialize(o); self.assertTrue(d["coach_final_authority"]); self.assertFalse(d["execution_authorized"])
if __name__=="__main__": unittest.main()
