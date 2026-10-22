import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import document_review
class ReviewedAllocations(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'evidence/deep_review').mkdir(parents=True);(self.root/'user_rules.json').write_text('{}')
  self.row=dict(id='bank1',direction='out',group='Внешняя',inn='9999999999',amount_cents=10000,purpose='Оплата по счету №111',account='account',date='2026-06-17',number='27',flags=['Нет подтверждённой привязки к объекту/заказу'])
  self.decision=dict(confirmed=True,reviewed_by='assistant',inn='9999999999',amount_cents=10000,number='111',allocations=[dict(deal_id='846',project='Проект',amount_cents=10000)],source='Проверенный рабочий проект',category='Подрядные работы')
 def tearDown(self):self.tmp.cleanup()
 def apply(self):
  (self.root/'evidence/deep_review/reviewed_allocations.json').write_text(json.dumps({'bank1':self.decision}))
  with patch.object(document_review,'ROOT',self.root):document_review.apply([self.row])
 def test_assistant_review_is_not_owner_confirmation(self):
  self.apply();self.assertEqual(self.row['status'],'Сверено по совокупности документов');self.assertEqual(self.row['category'],'Подрядные работы');self.assertFalse(self.row['flags'])
 def test_changed_bank_amount_is_rejected(self):
  self.row['amount_cents']=10001
  with self.assertRaises(AssertionError):self.apply()
 def test_incomplete_split_is_rejected(self):
  self.decision['allocations'][0]['amount_cents']=9999
  with self.assertRaises(AssertionError):self.apply()
 def test_different_invoice_is_rejected(self):
  self.row['purpose']='Оплата по счету №222'
  with self.assertRaises(AssertionError):self.apply()
