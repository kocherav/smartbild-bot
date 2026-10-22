import unittest
from payment_semantics import cash_form,invoice_cash_status,verify_cash_operation
class PaymentSemantics(unittest.TestCase):
 def test_no_invoice_no_income(self):
  with self.assertRaises(ValueError):cash_form(self.payment(),'2026-10-06')
 def payment(self):return dict(operation_type='31',kind='income',amount_cents=39012300,account_id='22',date='2026-09-23',document_number='2697',description='advance')
 def test_advance_explicitly_has_zero_goods(self):
  p=self.payment();p.update(crm_invoice_id='826',contractor_id='1002845');f=cash_form(p,'2026-10-06');self.assertEqual(f['Model[SecondarySum][Value]'],'0.00');self.assertEqual(f['Model[Invoice]'],'826');self.assertEqual(f['Model[Sum][Value]'],'390123.00')
 def test_supplier_payment_does_not_receive_goods(self):
  p=self.payment();p.update(kind='expense',operation_type='23',contractor_id='verified_supplier');self.assertEqual(cash_form(p,'2026-10-06')['Model[SecondarySum][Value]'],'0.00')
 def invoice(self,amounts,total=100):return {'sum':{'value':total,'currency':'RUB'},'financeOperations':[{'id':str(i),'kind':'income','incomeSum':{'value':a,'currency':'RUB'}} for i,a in enumerate(amounts)]}
 def test_partial_not_fully_paid(self):self.assertEqual(invoice_cash_status(self.invoice([40])),('drawn',4000))
 def test_split_full_payment(self):self.assertEqual(invoice_cash_status(self.invoice([40,60])),('paid',10000))
 def test_overpayment_held(self):
  with self.assertRaises(ValueError):invoice_cash_status(self.invoice([110]))
 def test_incomplete_payments_held(self):
  i=self.invoice([40]);i['financeOperationsCount']=2
  with self.assertRaises(ValueError):invoice_cash_status(i)
 def test_goods_default_detected(self):
  with self.assertRaisesRegex(ValueError,'goods'):verify_cash_operation({'Sum':{'Value':390123},'SecondarySum':{'Value':390123}},self.payment())

class CompanyMovementGuards(unittest.TestCase):
 def test_deposit_requires_bank_and_contract(self):
  from payment_semantics import verified_company_operation,expected_secondary_cents
  p=dict(allocation_scope='company',category='Возврат депозита',counterparty_inn='7743926877',kind='income',operation_type='30',contractor_id='1000609',deposit_contract='verified',amount_cents=10000)
  self.assertTrue(verified_company_operation(p));self.assertEqual(expected_secondary_cents(p),0)
  p['contractor_id']='wrong';self.assertFalse(verified_company_operation(p))
 def test_intercompany_never_ships(self):
  from payment_semantics import verified_company_operation,expected_secondary_cents
  p=dict(allocation_scope='company',category='Расчёты между компаниями группы',counterparty_inn='7743151323',kind='income',operation_type='31',intercompany_pair_id='verified',amount_cents=10000)
  self.assertTrue(verified_company_operation(p));self.assertEqual(expected_secondary_cents(p),0)
  p['counterparty_inn']='external';self.assertFalse(verified_company_operation(p))
 def test_receipt_identity_is_required(self):
  from payment_semantics import verified_company_operation,expected_secondary_cents
  p=dict(allocation_scope='company',category='ИТ и подписки',counterparty_inn='7728168971',kind='expense',operation_type='25',receipt_supplier_inn='9704259180',receipt_verified=True,card_last4='2624',amount_cents=10000)
  self.assertTrue(verified_company_operation(p));self.assertEqual(expected_secondary_cents(p),0)
  p['receipt_verified']=False;self.assertFalse(verified_company_operation(p))
 def test_refund_is_not_income_or_delivery(self):
  from payment_semantics import verified_company_operation,expected_secondary_cents
  p=dict(allocation_scope='company',category='Возвращённый аванс СТК',counterparty_inn='7704845920',kind='income',operation_type='30',refund_pair_id='verified',contractor_id='1002588',amount_cents=30000000)
  self.assertTrue(verified_company_operation(p));self.assertEqual(expected_secondary_cents(p),0)
  p['operation_type']='32';self.assertFalse(verified_company_operation(p))
