import unittest
from closing_documents import act_number

class ActNumberTests(unittest.TestCase):
 def test_stable_number_from_deal(self):
  self.assertEqual(act_number({'deal_id':'887'}),'887-АПП')
 def test_explicit_revision_number_preserved(self):
  self.assertEqual(act_number({'deal_id':'887','act_number':'887-АПП/1'}),'887-АПП/1')
 def test_missing_identifier_is_not_numberless_act(self):
  with self.assertRaises(ValueError):act_number({})
