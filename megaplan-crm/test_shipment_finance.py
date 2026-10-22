import copy,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
import shipment_finance as s

class Fake:
 def __init__(self):self.items=[];self.links=set();self.creates=0;self.fail_create=False;self.fail_link=False
 def list(self):return copy.deepcopy(self.items)
 def create(self,p):
  self.creates+=1
  f=s.form(p);o={'Id':str(self.creates),'Kind':'income','OperationType':{'Id':31},'Contractor':{'Id':p['contractor_id']},'RealAccount':{'Id':p['account_id']},'Date':f['Model[Date]'],'DocumentNumber':p['act_number'],'Description':f['Model[Description]'],'Sum':{'Value':0,'CurrencyId':1},'SecondarySum':{'Value':str(p['amount_cents']/100),'CurrencyId':1}}
  self.items.append(o)
  if self.fail_create:raise TimeoutError()
  return o['Id']
 def card(self,i):return next(copy.deepcopy(x) for x in self.items if str(x['Id'])==i)
 def linked(self,i,d):return (i,d) in self.links
 def link(self,i,d):
  self.links.add((i,d))
  if self.fail_link:raise TimeoutError()

class ShipmentFinanceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'ops.json';self.b=Fake()
  self.job={'mode':'live','deal_id':'894','data':{'payer':{'contractor':{'id':'100'}},'seller':{'accounts':['40702810902570001580']},'act_date':'13.10.2026','transfer_dates':{'goods':'30.09.2026','work':'13.10.2026'},'positions':[{'id':'1','kind':'goods','quantity':1,'total':'491200.00'},{'id':'2','kind':'work','quantity':1,'total':'217980.00'}],'total':'709180.00'}}
 def tearDown(self):self.tmp.cleanup()
 def test_dates_totals_and_zero_cash(self):
  ps=s.plans(self.job);self.assertEqual([x['date'] for x in ps],['2026-09-30','2026-10-13']);self.assertEqual(sum(x['amount_cents'] for x in ps),70918000)
  for p in ps:self.assertEqual(s.form(p)['Model[Sum][Value]'],'0.00')
 def test_required_control_date_is_internal_not_payment_due(self):
  p=s.plans(self.job)[0];f=s.form(p);self.assertEqual(f['Model[ControlDate]'],'2026-10-14');self.assertIn('не договорный срок оплаты',f['Model[Description]'])
 def test_test_mode_never_plans_operations(self):self.assertEqual(s.plans({'mode':'test'}),[])
 def test_replay_and_document_revision_do_not_duplicate(self):
  ps=s.plans(self.job);r=s.ensure(ps,self.b,self.path);self.job['id']='new-document-revision';s.ensure(s.plans(self.job),self.b,self.path)
  self.assertEqual(self.b.creates,2);self.assertEqual(len(r['operations']),2);self.assertEqual(len(self.b.links),2)
 def test_unsent_budget_pause_can_retry_without_uncertain_write(self):
  ps=s.plans(self.job)[:1]
  with patch.object(self.b,'create',side_effect=s.ProtectionPause('Бюджет. Запрос не отправлен.')):
   with self.assertRaises(s.ProtectionPause):s.ensure(ps,self.b,self.path)
  self.assertEqual(s.load(self.path)['operations'][ps[0]['key']]['state'],'unsent')
  s.ensure(ps,self.b,self.path);self.assertEqual(self.b.creates,1)
 def test_timeout_after_create_recovers_by_marker(self):
  ps=s.plans(self.job)[:1];self.b.fail_create=True
  with self.assertRaises(TimeoutError):s.ensure(ps,self.b,self.path)
  self.b.fail_create=False;s.ensure(ps,self.b,self.path);self.assertEqual(self.b.creates,1)
 def test_unknown_create_blocks_blind_retry(self):
  ps=s.plans(self.job)[:1];self.b.fail_create=True
  with self.assertRaises(TimeoutError):s.ensure(ps,self.b,self.path)
  self.b.items=[];self.b.fail_create=False
  with self.assertRaisesRegex(ValueError,'неизвестен'):s.ensure(ps,self.b,self.path)
  self.assertEqual(self.b.creates,1)
 def test_timeout_after_link_does_not_duplicate_finance(self):
  ps=s.plans(self.job)[:1];self.b.fail_link=True
  with self.assertRaises(TimeoutError):s.ensure(ps,self.b,self.path)
  self.b.fail_link=False;s.ensure(ps,self.b,self.path);self.assertEqual(self.b.creates,1)
 def test_changed_posted_sum_requires_correction(self):
  ps=s.plans(self.job);s.ensure(ps,self.b,self.path);ps[0]['amount_cents']+=1
  with self.assertRaisesRegex(ValueError,'другими данными'):s.ensure(ps,self.b,self.path)
 def test_wrong_cash_and_currency_rejected(self):
  p=s.plans(self.job)[0];ident=self.b.create(p);o=self.b.card(ident);o['Sum']['Value']=1
  with self.assertRaises(ValueError):s.verify(o,p)
  o=self.b.card(ident);o['SecondarySum']['CurrencyId']=2
  with self.assertRaises(ValueError):s.verify(o,p)
 def test_existing_unmarked_delivery_blocks_duplicate(self):
  p=s.plans(self.job)[0];self.b.create(p);self.b.items[0]['Description']='Ручная реализация'
  with self.assertRaisesRegex(ValueError,'похожая передача'):s.ensure([p],self.b,self.path)
  self.assertEqual(self.b.creates,1)
 def test_partial_identity_distinct_from_full(self):
  a=s.plans(self.job);self.job['shipment_id']='894-01';b=s.plans(self.job);self.assertNotEqual(a[0]['key'],b[0]['key'])
 def test_missing_party_or_mismatched_total_fail(self):
  self.job['data']['total']='1.00'
  with self.assertRaises(ValueError):s.plans(self.job)
  self.job['data']['payer']={}
  with self.assertRaises(ValueError):s.plans(self.job)
if __name__=='__main__':unittest.main()
