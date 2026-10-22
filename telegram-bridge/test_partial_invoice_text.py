import unittest
from partial_shipments import partial_invoice_text
class PartialInvoiceTextTest(unittest.TestCase):
 def data(self):return {'number':'1.890-1809/2026','date':'22.09.2026','act_number':'890-АПП/01','partial_payment':{'clause':'6.4.2','basis':'Договор '}}
 def test_contract_details_in_both_fields(self):
  line,basis=partial_invoice_text(self.data())
  self.assertEqual(basis,'Договор № 1.890-1809/2026 от 22.09.2026');self.assertIn(basis,line);self.assertIn('890-АПП/01',line);self.assertNotIn('; Договор',line)
 def test_meaningful_custom_basis_is_preserved(self):
  data=self.data();data['partial_payment']['basis']='Этап 2 согласован';line,basis=partial_invoice_text(data);self.assertTrue(line.endswith('; Этап 2 согласован'));self.assertNotIn('Этап',basis)
 def test_missing_contract_details_rejected(self):
  for key in ('number','date'):
   data=self.data();data[key]=''
   with self.assertRaises(ValueError):partial_invoice_text(data)
if __name__=='__main__':unittest.main()
