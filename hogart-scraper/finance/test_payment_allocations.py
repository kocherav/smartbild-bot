import unittest
from payment_allocations import normalize_allocations,allocation_key
from payment_semantics import cash_form,verified_company_operation
class SplitTests(unittest.TestCase):
 def test_mixed_cash(self):
  r={'id':'bank','amount_cents':11872688,'document_numbers':'054832;054835','confirmed_payment_allocations':[{'deal_id':'851','amount_cents':9889470,'invoice_number':'054832'},{'deal_id':'','amount_cents':1983218,'invoice_number':'054835','allocation_scope':'company','category':'Внепроектные закупки и услуги'}]}
  parts=normalize_allocations(r);self.assertEqual(sum(x['cents'] for x in parts),r['amount_cents']);self.assertNotEqual(allocation_key(r,parts[0],{}),allocation_key(r,parts[1],{}))
  p={'allocation_scope':'company','deal_id':'','category':'Внепроектные закупки и услуги','counterparty_inn':'7720298746','kind':'expense','operation_type':'25','amount_cents':1983218,'account_id':'20','date':'2026-05-12','document_number':'46','description':'test','contractor_id':'1002856'}
  self.assertTrue(verified_company_operation(p));self.assertEqual(cash_form(p,'2026-10-07')['Model[SecondarySum][Value]'],'0.00')
  r['confirmed_payment_allocations'][1]['amount_cents']+=90000
  with self.assertRaises(ValueError):normalize_allocations(r)
 def test_identity_and_bad_scope(self):
  r={'id':'b','amount_cents':100,'document_numbers':'1','confirmed_payment_allocations':[{'deal_id':'','amount_cents':100}]}
  with self.assertRaises(ValueError):normalize_allocations(r)
  a={'posting_key':'original','cents':100,'deal_id':'new','invoice':'1'};j={'original':{'bank_operation_id':'b','amount_cents':100}}
  self.assertEqual(allocation_key(r,a,j),'original');a['cents']=200
  with self.assertRaises(ValueError):allocation_key(r,a,j)
 def test_installer_purchase_has_no_delivery(self):
  p={'allocation_scope':'company','deal_id':'','category':'Закупки для Деревянко','counterparty_inn':'7717632694','kind':'expense','operation_type':'23','amount_cents':12478188,'account_id':'20','date':'2026-07-07','document_number':'84','description':'supplier payment, not installer deduction','contractor_id':'1003045'}
  self.assertTrue(verified_company_operation(p));self.assertEqual(cash_form(p,'2026-10-07')['Model[SecondarySum][Value]'],'0.00')
