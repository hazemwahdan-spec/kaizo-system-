import unittest
from reusable_knowledge_linkage import ReusableKnowledgeLinkage,serialize
class TestFeat050(unittest.TestCase):
 def test_valid(self):
  d=serialize(ReusableKnowledgeLinkage("link","knowledge","capability","coach")); self.assertTrue(d["coach_final_authority"]); self.assertFalse(d["execution_authorized"])
if __name__=="__main__": unittest.main()
