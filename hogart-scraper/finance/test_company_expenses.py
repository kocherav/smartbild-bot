import unittest
from post_confirmed import select_existing
class CompanyExpenseTests(unittest.TestCase):
 def setUp(self):
  self.p={'allocation_scope':'company','account_id':'20','date':'2026-10-06','kind':'expense','amount_cents':25000,'document_number':'2','marker':'BANK:test'}
 def op(self,n,ident):return {'Id':ident,'RealAccount':{'Id':20},'Date':'2026-10-06','Kind':'expense','Sum':{'Value':250},'DocumentNumber':n}
 def test_distinct_number_same_amount_is_new(self):self.assertIsNone(select_existing([self.op('1',10)],self.p))
 def test_exact_number_reused_among_other_fees(self):self.assertEqual(select_existing([self.op('1',10),self.op('2',11)],self.p)['Id'],11)
 def test_missing_number_still_ambiguous(self):
  with self.assertRaises(ValueError):select_existing([self.op('',10)],self.p)
 def test_duplicate_number_is_ambiguous(self):
  with self.assertRaises(ValueError):select_existing([self.op('2',10),self.op('2',11)],self.p)
class CompanyIncomeTests(unittest.TestCase):
 def payment(self):return dict(allocation_scope='company',category='Проценты по депозиту',kind='income',operation_type='32',counterparty_inn='7728168971',contractor_id='1000609',amount_cents=10000,account_id='20',date='2026-10-06',document_number='1',description='Bank interest',deal_id='')
 def test_bank_interest_without_sales_invoice(self):
  from payment_semantics import cash_form
  form=cash_form(self.payment(),'2026-10-06');self.assertNotIn('Model[Invoice]',form);self.assertEqual(form['Model[SecondarySum][Value]'],'100.00')
 def test_other_payer_still_requires_invoice(self):
  from payment_semantics import cash_form
  p=self.payment();p['counterparty_inn']='1234567890'
  with self.assertRaises(ValueError):cash_form(p,'2026-10-06')
 def test_sales_still_require_invoice(self):
  from payment_semantics import cash_form
  p=self.payment();p['operation_type']='31'
  with self.assertRaises(ValueError):cash_form(p,'2026-10-06')

class CommissionSemanticsTests(unittest.TestCase):
 def test_commission_is_settled_not_bank_receivable(self):
  from payment_semantics import expected_secondary_cents,verify_cash_operation
  p=dict(allocation_scope='company',category='Банковские комиссии',kind='expense',operation_type='25',counterparty_inn='7728168971',contractor_id='1000609',amount_cents=24900,account_id='22',deal_id='')
  self.assertEqual(expected_secondary_cents(p),24900)
  o=dict(Sum={'Value':249},SecondarySum={'Value':249},RealAccount={'Id':22},Kind='expense',OperationType={'Id':25},Status='closed')
  verify_cash_operation(o,p)
  o['SecondarySum']['Value']=0
  with self.assertRaises(ValueError):verify_cash_operation(o,p)

class ReviewedCompanyTests(unittest.TestCase):
 def test_tax_payment_does_not_recognize_expense(self):
  from payment_semantics import expected_secondary_cents,verified_company_operation,semantics_label
  p=dict(allocation_scope='company',category='Единый налоговый платёж',counterparty_inn='7727406020',kind='expense',operation_type='25',amount_cents=10000)
  self.assertTrue(verified_company_operation(p));self.assertEqual(expected_secondary_cents(p),0);self.assertEqual(semantics_label(p),'cash_only')
  p['counterparty_inn']='1234567890';self.assertFalse(verified_company_operation(p))
 def test_loan_interest_is_not_sale_or_principal(self):
  from payment_semantics import verified_company_operation,expected_secondary_cents
  p=dict(allocation_scope='company',category='Проценты по займу',counterparty_inn='7807391482',kind='income',operation_type='32',amount_cents=10000)
  self.assertTrue(verified_company_operation(p));self.assertEqual(expected_secondary_cents(p),10000)
  p['category']='Возврат займа';self.assertFalse(verified_company_operation(p))

if __name__=='__main__':unittest.main()
