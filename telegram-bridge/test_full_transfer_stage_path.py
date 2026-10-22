import unittest
from unittest.mock import patch,Mock
import partial_shipments as p,closing_runtime as c
class FullTransferPathTests(unittest.TestCase):
 def test_invoice_stage_follows_production_without_fake_payment(self):
  state=['133'];moves=[]
  def call(method,path,**kw):
   if method=='POST':
    target=kw['json_body']['id'];moves.append(target);state[0]=target;return {'data':{}}
   nexts={'133':['134','135'],'135':['136'],'136':['138'],'138':[]}[state[0]]
   return {'data':{'id':'7','state':{'id':state[0]},'possibleTransitions':[{'id':n,'to':{'id':n},'enabled':True} for n in nexts]}}
  crm=Mock();crm._call.side_effect=call
  with patch.object(p.workspace,'complete_volume',return_value=True),patch.object(c,'api',return_value=crm),patch.object(c,'effect',side_effect=lambda j,n,f:f()),patch('deal_browser.update_cached_deal'):
   p.to_ship({'id':'job','deal_id':'7'});p.to_ship({'id':'job','deal_id':'7'})
  self.assertEqual(['135','136','138'],moves)
 def test_disabled_or_backward_transitions_are_not_used(self):
  crm=Mock();crm._call.return_value={'data':{'state':{'id':'136'},'possibleTransitions':[{'id':'a','to':{'id':'135'}},{'id':'b','to':{'id':'138'},'enabled':False}]}}
  with patch.object(p.workspace,'complete_volume',return_value=True),patch.object(c,'api',return_value=crm),patch.object(c,'effect') as effect:
   with self.assertRaises(ValueError):p.to_ship({'deal_id':'7'})
   effect.assert_not_called()
 def test_finance_receipt_persisted_before_stage_failure(self):
  from shipment_finance import Backend
  receipt={'ok':True,'operations':[{'id':'existing'}]};job={'id':'j','mode':'live','shipment_id':'j'};reg=Mock();reg.patch.return_value={**job,'shipment_finance':receipt}
  with patch.object(c.Path,'exists',return_value=True),patch.object(c,'api'),patch.object(c,'validate_current'),patch('shipment_finance.plans',return_value=[]),patch('shipment_finance.Backend'),patch('shipment_finance.ensure',return_value=receipt),patch.object(c,'registry',return_value=reg),patch.object(p,'to_ship',side_effect=ValueError('stage')):
   with self.assertRaises(ValueError):c.record_transfer(job)
  reg.patch.assert_called_once_with('j',shipment_finance=receipt)
if __name__=='__main__':unittest.main()
