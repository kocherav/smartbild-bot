import unittest,tempfile
from pathlib import Path
from datetime import datetime
from closing_workflow import *
class ClosingTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.r=Registry(Path(self.tmp.name)/'state.json')
 def tearDown(self):self.tmp.cleanup()
 def test_baseline_and_transition_once(self):
  self.assertIsNone(self.r.observe('887','138'));self.r.observe('887','136');a=self.r.observe('887','138');self.assertEqual(a['mode'],'live');self.assertIsNone(self.r.observe('887','138'));self.assertEqual(a,self.r.enqueue('887'))
 def test_test_mode_cannot_confirm_or_swallow_live(self):
  t=self.r.enqueue('887','test');self.r.patch(t['id'],status='awaiting_edo')
  with self.assertRaises(ValueError):self.r.confirm(t['id'],'1','1',dict(act='a',upd='u',invoice='s'),datetime.now())
  self.assertNotEqual(t['id'],self.r.enqueue('887')['id'])
 def test_confirmation_actor_and_all_documents(self):
  j=self.r.enqueue('887');self.r.patch(j['id'],status='awaiting_edo')
  for actor,refs in [('2',dict(act='a',upd='u',invoice='s')),('1',dict(act='a',upd='u'))]:
   with self.assertRaises(ValueError):self.r.confirm(j['id'],actor,'1',refs,datetime.now())
  a=self.r.confirm(j['id'],'1','1',dict(act='a',upd='u',invoice='s'),datetime.now());self.assertEqual(a['status'],'edo_confirmed')
 def test_final_clause_not_second_advance(self):
  self.assertEqual(final_clause('6.4.2 Авансовый платеж 100 рублей\n6.4.3 Окончательный расчет 200 рублей\n7. ОТВЕТСТВЕННОСТЬ'),'6.4.3')
  with self.assertRaises(ValueError):final_clause('6.4.2 Окончательный расчет\n6.4.3 Окончательный расчет')
 def test_next_business_day_holiday(self):
  self.assertEqual(next_business_day(datetime(2026,11,3,12)).date(),date(2026,11,5))
  self.assertEqual(next_business_day(datetime(2026,10,16)).date(),date(2026,10,19))
 def tx(self,amount='627623.00',**kw):return dict({'id':'a','date':'12.10.2026','document_number':'1','deal_id':'887','status':'assigned','counterparty_inn':'payer','account':'our','amount':amount,'direction':'income'},**kw)
 def test_no_rounding_off_17_kopecks_and_duplicates(self):
  job=dict(deal_id='887',mode='live',edo_confirmation=True,payer_inn='payer',seller_accounts=['our'],total_cents=62762317);deal=dict(state={'id':'137'},price={'value':627623.17})
  self.assertFalse(bank_closure_allowed(job,deal,[self.tx(),self.tx()])[0]);self.assertTrue(bank_closure_allowed(job,deal,[self.tx(),self.tx('0.17',id='b')])[0])
  self.assertFalse(bank_closure_allowed(job,deal,[self.tx('627623.17'),self.tx('1',id='r',direction='expense',purpose='Возврат')])[0])
 def test_wrong_payer_unassigned_email_and_test_never_close(self):
  for kw in [dict(counterparty_inn='other'),dict(status='unassigned'),dict(source='email'),dict(account='other')]:self.assertEqual(settled_amount([self.tx(**kw)],'887','payer',['our'])[0],0)
 def test_conflicting_duplicate_is_error(self):
  with self.assertRaises(ValueError):settled_amount([self.tx('1'),self.tx('2')],'887','payer',['our'])
if __name__=='__main__':unittest.main()
