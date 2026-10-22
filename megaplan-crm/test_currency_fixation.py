import unittest,copy
import currency_fixation as f
class FixationTests(unittest.TestCase):
 def deal(self):
  return {'id':'1','price':{'currency':'RUB','value':500},'positions':[{'id':'a','offer':{'id':'o'},'quantity':3,'price':{'currency':'USD','value':10},'sum':{'currency':'USD','value':27},'discount':{'type':'percent','valueInMain':10}},{'id':'b','offer':{'id':'p'},'quantity':1,'price':{'currency':'RUB','value':100},'sum':{'currency':'RUB','value':100},'discount':None}]}
 def test_derived_rate_discount_once_and_exact_total(self):
  p=f.plan(self.deal(),'343',{'a':'27','b':'100'},'hash','2026-07-24');self.assertEqual(p['derived_rate'],'9');self.assertEqual(p['targets'][0]['unit_rub'],'90.0000');self.assertEqual(p['targets'][0]['total_cents'],24300)
 def test_partial_mapping_or_changed_ruble_line_rejected(self):
  with self.assertRaises(ValueError):f.plan(self.deal(),343,{'a':27},'h','d')
  with self.assertRaises(ValueError):f.plan(self.deal(),343,{'a':27,'b':99},'h','d')
 def test_apply_resume_and_no_duplicate_write(self):
  d=self.deal();p=f.plan(d,343,{'a':27,'b':100},'h','d');outer=self
  class API:
   def __init__(self):self.data=copy.deepcopy(d);self.writes=0
   def _call(self,method,path):
    outer.assertEqual((method,path),('GET','/deal/1'));return {'data':copy.deepcopy(self.data)}
   def update_offer_row_price(self,rid,price):
    self.writes+=1;r=self.data['positions'][0];r['price']={'currency':'RUB','value':price};r['sum']={'currency':'RUB','value':243};self.data['price']={'currency':'RUB','value':343}
  api=API();progress={};f.apply(api,p,progress,lambda:None);f.apply(api,p,progress,lambda:None);self.assertEqual(api.writes,1);self.assertTrue(progress['a']['verified'])
  api.data['positions'][0]['quantity']=4
  with self.assertRaisesRegex(ValueError,'изменена'):f.apply(api,p,progress,lambda:None)
if __name__=='__main__':unittest.main()
