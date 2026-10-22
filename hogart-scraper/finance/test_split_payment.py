import unittest
from post_confirmed import select_existing
class SplitPaymentTests(unittest.TestCase):
 def payment(self):return dict(marker='BANK:first',sibling_markers=['BANK:first','BANK:second'],account_id='20',date='2026-08-14',kind='expense',amount_cents=819150,document_number='112')
 def operation(self,marker,number='112'):return dict(Id='1',Description='['+marker+']',RealAccount={'Id':'20'},Date='2026-08-14 12:00:00',Kind='expense',Sum={'Value':8191.5},DocumentNumber=number)
 def test_equal_sibling_is_not_reused(self):self.assertIsNone(select_existing([self.operation('BANK:second')],self.payment()))
 def test_own_marker_reused(self):self.assertEqual(select_existing([self.operation('BANK:first'),self.operation('BANK:second')],self.payment())['Id'],'1')
 def test_unknown_marker_not_ignored(self):self.assertIsNotNone(select_existing([self.operation('BANK:unknown')],self.payment()))
 def test_sibling_marker_on_other_document_is_held(self):
  with self.assertRaises(ValueError):select_existing([self.operation('BANK:second','113')],self.payment())
