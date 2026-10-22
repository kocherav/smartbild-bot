import tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import partial_shipments as p,closing_runtime as c
from workflow_runtime import Store

class PartialInvoiceRecoveryTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.db=Path(self.tmp.name)/'workflow.db';self.store=Store(self.db)
  op=self.store.create('closing','create-partial-invoice','intent',{'deal':'890'},{})
  self.store.confirm(op['id'],op['revision']);self.store.claim(op['id']);self.store.finish(op['id'],{'ok':False},status='uncertain')
  self.ident=op['id'];self.job={'id':'job','deal_id':'890','receipts':{'create-partial-invoice':{'_operation_id':self.ident}},'data':{'payer_id':'customer','partial_payment':{'amount':'152200'}}}
  self.crm=Mock();self.crm._call.side_effect=lambda method,url,**kw:{'data':{'invoices':[{'id':'836'}]} if url.startswith('/deal/') else {'id':'836','rows':[{'name':'Расчёт'}]}}
 def test_uncertain_success_reconciles_without_any_creation(self):
  with patch.object(c,'DB',self.db),patch('contract_invoice.verify_created_invoice',return_value={'id':'836','number':'10499'}) as verify:
   p.reconcile_partial_invoice(self.job,self.crm,'Расчёт ','7');verify.assert_called_once()
   p.reconcile_partial_invoice(self.job,self.crm,'Расчёт ','7');verify.assert_called_once()
  op=self.store.get(self.ident);self.assertEqual('succeeded',op['status']);self.assertEqual('836',op['receipt']['invoice_id'])
  self.assertTrue(all(call.args[0]=='GET' for call in self.crm._call.call_args_list))
 def test_missing_invoice_stays_uncertain(self):
  self.crm._call.return_value={'data':{'invoices':[]}};self.crm._call.side_effect=None
  with patch.object(c,'DB',self.db),self.assertRaisesRegex(ValueError,'найдено 0'):p.reconcile_partial_invoice(self.job,self.crm,'Расчёт','7')
  self.assertEqual('uncertain',self.store.get(self.ident)['status'])
 def test_failed_verification_never_confirms(self):
  with patch.object(c,'DB',self.db),patch('contract_invoice.verify_created_invoice',side_effect=ValueError('wrong sum')),self.assertRaises(ValueError):p.reconcile_partial_invoice(self.job,self.crm,'Расчёт','7')
  self.assertEqual('uncertain',self.store.get(self.ident)['status'])
if __name__=='__main__':unittest.main()
