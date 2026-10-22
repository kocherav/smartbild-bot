import copy,unittest
from unittest.mock import Mock,patch
import contract_invoice as c

class InvoiceReadbackTest(unittest.TestCase):
 def setUp(self):
  self.line='Частичный расчёт по акту 890-АПП/01, п. 6.4.2 договора. Основание: Договор '
  self.data={'deal_id':'890','payer_id':'customer','basis':self.line}
  self.rows=[{'name':self.line,'quantity':1,'price':'152200','tax_id':'7'}]
  self.invoice={'id':'836','number':'10499','deal':{'id':'890'},'payer':{'id':'customer'},'recipient':{'id':'seller'},'invoiceTemplate':{'id':'3'},'status':'drawn','rows':[{'name':self.line.strip(),'quantity':1,'price':{'value':152200},'tax':{'id':'7'}}],'sum':{'value':152200,'currency':'RUB'}}
  self.api=Mock();self.api._call.side_effect=lambda *a,**k:{'data':self.invoice}
  self.patches=[patch('seller_documents.invoice_settings',return_value=('seller','3')),patch.object(c,'v1_call',return_value={'data':{'invoice':{'PaymentOrderNumber':self.line.strip()}}})]
  for p in self.patches:p.start();self.addCleanup(p.stop)
 def test_real_trailing_space_case_succeeds(self):
  self.assertEqual(c.verify_created_invoice(self.api,'836',self.data,self.rows)['id'],'836')
 def test_different_basis_not_normalized_away(self):
  self.data['basis']='Другой договор'
  with self.assertRaises(ValueError):c.verify_created_invoice(self.api,'836',self.data,self.rows)
 def test_wrong_financial_or_party_fields_rejected(self):
  original=copy.deepcopy(self.invoice)
  for field,value in [('sum',{'value':152201,'currency':'RUB'}),('payer',{'id':'other'}),('status','draft'),('rows',[{**original['rows'][0],'tax':{'id':'5'}}])]:
   self.invoice=copy.deepcopy(original);self.invoice[field]=value
   with self.subTest(field=field),self.assertRaises(ValueError):c.verify_created_invoice(self.api,'836',self.data,self.rows)
if __name__=='__main__':unittest.main()
