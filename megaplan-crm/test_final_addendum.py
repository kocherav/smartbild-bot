import unittest,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
from closing_documents import price_addendum

class FinalAddendumTests(unittest.TestCase):
 def data(self,**kw):
  return dict(deal_id='999',number='1.999',date='01.09.2026',act_date='16.10.2026',payer_name='ООО Заказчик',payer={'inn':'1234567890'},signatory={'position':'Директор','name':'Иванов','authority':'Устав'},seller={'id':'cliwell'},positions=[{'tax_rate':5}],**kw)
 def policy(self,clause='6.4.2'):
  return {'payments':{'6.4.1':{'gross':'100'},clause:{'base':'200','gross':'210'}},'vat':'10','gross_total':'310','transfer_dates':{'goods':'30.09.2026'}}
 def test_final_pdf_source_and_filename_for_any_deal_and_clause(self):
  for clause in ['6.4.2','6.4.3']:
   with tempfile.TemporaryDirectory() as out,patch('document_tax_policy.approved_deal',return_value=self.policy(clause)),patch('weasyprint.HTML') as render:
    path=price_addendum(self.data(),out);html=render.call_args.kwargs['string']
    self.assertNotIn('проект',html.lower());self.assertNotIn('проект',path.lower());self.assertIn('999',Path(path).name)
    self.assertIn('п. '+clause,html);self.assertIn('310,00',html);self.assertIn('1234567890',html);self.assertIn('width:40mm',html)
 def test_partial_taxable_work_includes_agreement_but_september_goods_dont(self):
  with tempfile.TemporaryDirectory() as out,patch('document_tax_policy.approved_deal',return_value=self.policy()),patch('weasyprint.HTML'):
   d=self.data(partial=True);self.assertIsNotNone(price_addendum(d,out))
   d['positions']=[{'tax_rate':-1}];self.assertIsNone(price_addendum(d,out))
 def test_no_unapproved_terms_or_wrong_seller(self):
  with patch('document_tax_policy.approved_deal',return_value={}):self.assertIsNone(price_addendum(self.data(),'/unused'))
  with patch('document_tax_policy.approved_deal',return_value=self.policy()):
   d=self.data();d['seller']['id']='insis';self.assertIsNone(price_addendum(d,'/unused'))
 def test_inconsistent_amounts_block_generation(self):
  p=self.policy();p['gross_total']='999'
  with patch('document_tax_policy.approved_deal',return_value=p):
   with self.assertRaises(ValueError):price_addendum(self.data(),'/unused')
 def test_partial_prepare_calls_shared_generator(self):
  from test_historical_partial_prepare import HistoricalPrepareTests
  with patch('closing_documents.price_addendum',return_value=None) as make:
   HistoricalPrepareTests().run_prepare('30.09.2026')
   self.assertTrue(make.call_args.args[0]['partial'])
