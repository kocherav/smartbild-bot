import unittest,json,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
from decimal import Decimal
import document_tax_policy as t
class VatTransitionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.file=Path(self.tmp.name)/'tax.json'
  self.policy={'companies':{'cliwell':[{'from':'2020-01-01','rate':-1},{'from':'2026-10-01','rate':5}],'insis':[{'from':'2026-01-01','rate':22}]},'deals':{'887':{'rows':{'1':{'rate':-1,'base_total':'390123.17','gross':'390123.17'},'2':{'rate':5,'base_total':'237500.00','gross':'249375.00'}},'payments':{'6.4.2':{'base':'237500.00','gross':'249375.00','rate':5}}}}}
  self.file.write_text(json.dumps(self.policy));self.patch=patch.object(t,'POLICY_FILE',self.file);self.patch.start();self.addCleanup(self.patch.stop)
 def test_effective_dates_and_legal_entities(self):
  self.assertEqual(t.company_rate('cliwell','2026-09-30'),-1);self.assertEqual(t.company_rate('cliwell','2026-10-01'),5);self.assertEqual(t.company_rate('insis','2026-10-13'),22)
 def test_gross_tax_not_added_twice(self):
  self.assertEqual(t.vat('249375',5),Decimal('11875.00'));self.assertEqual(t.vat('390123.17',-1),0)
 def test_creation_policy_keeps_approved_sale_prices(self):
  x={'tax_mode':'none','unit_price':105};self.assertEqual(t.creation_rate(x),'5');self.assertEqual(x['unit_price'],105)
 def test_insis_not_overwritten(self):
  self.assertEqual(t.creation_rate({'seller_id':'insis','tax_mode':'none'}),'22')
 def deal(self):return {'id':'887','positions':[{'id':'1','sum':{'value':390123.17},'tax':{'rate':-1}},{'id':'2','sum':{'value':249375},'tax':{'rate':5}}]}
 def test_transition_requires_exact_rows_rates_and_totals(self):
  self.assertEqual(t.require_document_tax(self.deal(),Mock()),[-1,5]);d=self.deal();d['positions'][1]['sum']['value']=237500
  with self.assertRaises(ValueError):t.require_document_tax(d,Mock())
 def test_stage_payment_tax_and_price(self):
  api=Mock();api.resolve_tax_id.return_value='8';r=t.payment_tax({'clause':'6.4.2','amount':237500,'line':'сумма 237 500,00 руб.'},self.deal(),api)
  self.assertEqual(r['amount'],249375);self.assertEqual(r['vat_amount'],'11875.00');self.assertEqual(r['tax_id'],'8')
 def test_changed_contract_amount_not_silently_repriced(self):
  with self.assertRaises(ValueError):t.payment_tax({'clause':'6.4.2','amount':1,'line':'x'},self.deal(),Mock())
 def test_mixed_act_total(self):
  d=t.decorate({'positions':[{'total':'390123.17'},{'total':'249375.00'}]},[-1,5]);self.assertEqual(d['vat_amount'],'11875.00');self.assertIn('5%',d['tax_text'])
 def test_profit_excludes_output_vat(self):
  from build_profitability_report import compute_profitability
  rows,revenue,cost,profit,margin=compute_profitability([{'name':'Работы','qty':1,'sell_price':105,'tax_rate':5,'cost_material':0,'cost_work':20}],procurement={},installation={})
  self.assertAlmostEqual(revenue,100);self.assertAlmostEqual(profit,80)
 def test_tax_reference_in_ledger_is_resolved_not_assumed_exempt(self):
  self.policy['tax_ids']={'8':5};self.file.write_text(json.dumps(self.policy))
  self.assertEqual(t.stored_row_rate({'tax':{'id':'8'}}),5)
  with self.assertRaises(ValueError):t.stored_row_rate({'tax':{'id':'unknown'}})
 def test_historical_rates_still_calculate(self):
  self.assertEqual(t.vat(120,20),Decimal('20.00'))
