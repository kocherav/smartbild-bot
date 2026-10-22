import tempfile,unittest,json
from pathlib import Path
import allocation_apply as a
class AllocationApplyTests(unittest.TestCase):
 def test_plan_existing_capacity_and_surplus(self):
  entries={'1':[{'offer_row_id':'r','offer_id':'o','name':'Кабель','qty':2,'consumed_qty':1}]}
  plan={'allocations':[{'line_id':'s','deal_id':'1','qty':'1','amount_cents':100,'name':'Кабель'}]}
  result=a.targets(plan,entries);self.assertEqual(result[0]['offer_row_id'],'r')
  plan['allocations'][0]['qty']='2';self.assertEqual(a.targets(plan,entries)[0]['cost_kind'],'expense')
 def test_no_empty_apply(self):
  with self.assertRaises(ValueError):a.targets({'allocations':[]},{})

class ExecutionTests(unittest.TestCase):
 def setUp(self):
  import copy
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);(self.root/'data').mkdir();(self.root/'ledger').mkdir()
  self.proc=self.root/'proc.json'
  self.data={'invoices':[{'document_key':'i','number':'10','supplier':'S','total':100,'allocations':[],'payments':[]}], 'unallocated_stock':[{'id':'s','document_key':'i','name':'Кабель','source_line_key':'k','initial_qty':4,'available_qty':4,'available_amount':100,'allocations':[]}]}
  self.rows=[{'offer_row_id':'r','offer_id':'o','name':'Кабель','qty':4,'consumed_qty':0,'cost_material':0,'cost_work':2,'sell_price':100,'cumulative_cost_material':0}]
  self.proc.write_text(json.dumps(self.data));(self.root/'ledger/1.json').write_text(json.dumps(self.rows));(self.root/'data/review_registry.json').write_text(json.dumps({'allocation_drafts':{}}))
  self.body={'document_key':'i','source_revision':a.workspace.fingerprint(a.workspace.source_document(self.data,'i')),'draft_revision':0,'allocations':[{'line_id':'s','deal_id':'1','qty':4}]}
  self.deals=[{'id':'1','name':'Test'}];self.loader=lambda did:json.loads((self.root/'ledger'/f'{did}.json').read_text())
 def queue(self):
  plan=a.prepare(self.body,self.deals,self.data,self.loader);self.body['apply_revision']=plan['apply_revision']
  a.request(self.body,self.deals,77,self.root,self.proc,self.loader)
  return json.loads((self.root/'data/review_registry.json').read_text())['allocation_drafts']['i']['execution']
 def test_commit_exactly_once_and_preserves_sales_payments(self):
  job=self.queue();a.commit(job,self.proc,self.root/'ledger');first=self.proc.read_text();a.commit(job,self.proc,self.root/'ledger')
  self.assertEqual(first,self.proc.read_text());row=self.loader('1')[0];self.assertEqual(row['cost_material'],25);self.assertEqual(row['consumed_qty'],4);self.assertEqual(row['sell_price'],100);self.assertEqual(row['cost_work'],2)
  data=json.loads(first);self.assertEqual(data['invoices'][0]['allocations'],[]);self.assertEqual(data['invoices'][0]['payments'],[]);self.assertEqual(data['unallocated_stock'][0]['available_qty'],0)
  self.assertEqual(a.request(self.body,self.deals,77,self.root,self.proc,self.loader)['id'],job['id'])
 def test_stale_ledger_or_source_prevents_writes(self):
  job=self.queue();self.rows[0]['sell_price']=101;(self.root/'ledger/1.json').write_text(json.dumps(self.rows));before=self.proc.read_text()
  with self.assertRaisesRegex(ValueError,'Экономика'):a.commit(job,self.proc,self.root/'ledger')
  self.assertEqual(before,self.proc.read_text())
 def test_crash_between_ledger_and_registry_resumes_absolute(self):
  from unittest.mock import patch
  job=self.queue();real=a.queue.atomic
  def crash(path,value):
   if path==self.proc:raise OSError('crash')
   real(path,value)
  with patch.object(a.queue,'atomic',side_effect=crash):
   with self.assertRaises(OSError):a.commit(job,self.proc,self.root/'ledger')
  self.assertEqual(self.loader('1')[0]['consumed_qty'],4)
  a.commit(job,self.proc,self.root/'ledger');self.assertEqual(self.loader('1')[0]['consumed_qty'],4)
  self.assertEqual(len(json.loads(self.proc.read_text())['unallocated_stock'][0]['allocations']),1)
 def test_projection_and_extra_expense_count_once(self):
  from procurement_projection import effective_registry
  from unittest.mock import patch
  import build_profitability_report as report
  self.rows[0]['consumed_qty']=4;(self.root/'ledger/1.json').write_text(json.dumps(self.rows));job=self.queue()
  self.assertEqual(job['plan']['targets'][0]['cost_kind'],'expense');a.commit(job,self.proc,self.root/'ledger')
  raw=json.loads(self.proc.read_text());projected=effective_registry(raw)
  self.assertEqual(len(raw['invoices'][0]['allocations']),0);self.assertEqual(len(projected['invoices'][0]['allocations']),1)
  with patch.object(report,'PROCUREMENT_REGISTRY',str(self.proc)):
   items=report.load_procurement_items('1');self.assertEqual(sum(x['amount'] for x in items['__additional_expenses__']),100)
   _,revenue,cost,profit,_=report.compute_profitability([],items,{},'1');self.assertEqual((revenue,cost,profit),(0,100,-100))
 def test_worker_failure_and_retry_keeps_registry_step(self):
  import sys
  sys.path.insert(0,str(a.CRM.parent/'telegram-bridge'))
  import allocation_runtime as runtime
  from unittest.mock import patch
  job=self.queue();real=a.commit
  with patch.object(a,'commit',side_effect=lambda j:real(j,self.proc,self.root/'ledger')) as commit,patch.object(runtime,'sync_deal',side_effect=ValueError('CRM offline')):
   runtime.process('i',job,object(),self.root);self.assertEqual(job['state'],'error');self.assertTrue(job['steps']['registry']);self.assertEqual(commit.call_count,1)
  a.request(self.body,self.deals,77,self.root,self.proc,self.loader)
  job=json.loads((self.root/'data/review_registry.json').read_text())['allocation_drafts']['i']['execution']
  with patch.object(a,'commit') as commit,patch.object(runtime,'sync_deal',return_value={'verified':True,'cost':100,'profit':300}):
   runtime.process('i',job,object(),self.root);commit.assert_not_called();self.assertEqual(job['state'],'completed')
  reg=json.loads((self.root/'data/review_registry.json').read_text());self.assertTrue(reg['allocation_drafts']['i']['crm_applied']);self.assertEqual(len([x for x in reg['workflow_audit'] if x['action']=='allocation_completed']),1)
 def test_preview_revision_required_and_private_ledger_hidden(self):
  self.body['apply_revision']='old'
  with self.assertRaises(a.workspace.Conflict):a.request(self.body,self.deals,77,self.root,self.proc,self.loader)
  job=self.queue();self.assertNotIn('ledger_before',a.public_job(job)['plan'])
  doc=a.workspace.public_document(a.workspace.source_document(self.data,'i'),json.loads((self.root/'data/review_registry.json').read_text()))
  self.assertNotIn('ledger_before',doc['draft']);self.assertNotIn('ledger_before',doc['draft']['execution']['plan'])
 def test_crm_write_verified_and_cost_not_accumulated_on_retry(self):
  import sys,copy
  sys.path.insert(0,str(a.CRM.parent/'telegram-bridge'))
  import allocation_runtime as runtime,deal_ledger,build_profitability_report as report
  from megaplan_api import MegaplanAPI
  from unittest.mock import patch
  job=self.queue();a.commit(job,self.proc,self.root/'ledger')
  class API:
   _cost_fields=staticmethod(MegaplanAPI._cost_fields)
   ledger_from_deal=staticmethod(MegaplanAPI.ledger_from_deal)
   def __init__(self):
    self.offer={'id':'o','name':'Кабель',**self._cost_fields(0,2)};self.profit=0;self.writes=[];self.total=400;self.reprice_on_write=False
   def _call(self,method,path,**kw):
    if method=='POST':
     if self.reprice_on_write:self.total=390
     self.writes.append((path,kw));self.profit=kw['json_body']['Category1000068CustomFieldRentabelnost']['value'];return {'data':{}}
    if path=='/offer/o':return {'data':copy.deepcopy(self.offer)}
    return {'data':{'price':{'value':self.total},'Category1000068CustomFieldRentabelnost':{'value':self.profit},'positions':[{'id':'r','offer':copy.deepcopy(self.offer),'quantity':4,'price':{'value':100},'sum':{'value':400}}]}}
   def update_offer_cost(self,oid,cost_material):self.writes.append(('offer',cost_material));self.offer.update(self._cost_fields(cost_material,None))
  api=API()
  with patch.object(deal_ledger,'LEDGER_DIR',str(self.root/'ledger')),patch.object(report,'PROCUREMENT_REGISTRY',str(self.proc)),patch.object(report,'load_installation_items',return_value={}):
   first=runtime.sync_deal(job,'1',api);self.assertTrue(first['verified']);self.assertFalse(first['cash_operations_changed']);writes=len(api.writes)
   second=runtime.sync_deal(job,'1',api);self.assertEqual(first,second);self.assertEqual(writes,len(api.writes));self.assertEqual(first['revenue'],400)
   api.profit=0;api.reprice_on_write=True
   with self.assertRaisesRegex(ValueError,'изменил сумму продажи'):runtime.sync_deal(job,'1',api)
   api.reprice_on_write=False;api.total=400
   api.offer.update(api._cost_fields(None,1000));writes=len(api.writes)
   with self.assertRaisesRegex(ValueError,'базу себестоимости'):runtime.sync_deal(job,'1',api)
   self.assertEqual(len(api.writes),writes,'Ambiguous unit/line cost must not rewrite profit')
   api.offer.update(api._cost_fields(None,2))
   api.offer.update(api._cost_fields(99,None))
   with self.assertRaisesRegex(ValueError,'Себестоимость позиции изменена'):runtime.sync_deal(job,'1',api)
 def test_ledger_atomic_save_keeps_dashboard_read_mask(self):
  import deal_ledger
  path=self.root/'ledger/1.json';path.chmod(0o600);deal_ledger.atomic_json(str(path),self.rows)
  self.assertTrue(path.stat().st_mode & 0o040);self.assertEqual(path.stat().st_mode & 0o007,0)

 def test_transient_crm_busy_retries_without_repeating_registry(self):
  import sys
  sys.path.insert(0,str(a.CRM.parent/'telegram-bridge'))
  import allocation_runtime as runtime
  from unittest.mock import patch
  job=self.queue();real=a.commit
  with patch.object(a,'commit',side_effect=lambda j:real(j,self.proc,self.root/'ledger')),patch.object(runtime,'sync_deal',side_effect=ValueError('Мегаплан: очередь запросов занята. Запрос не отправлен; повторите позже.')):
   runtime.process('i',job,object(),self.root)
  self.assertEqual(job['state'],'queued');self.assertEqual(job['retry_attempts'],1);self.assertTrue(job['steps']['registry'])
  with patch.object(a,'commit') as commit,patch.object(runtime,'sync_deal',return_value={'verified':True}):
   runtime.process('i',job,object(),self.root);commit.assert_not_called();self.assertEqual(job['state'],'completed')

class CurrencyPreflightTests(unittest.TestCase):
 def test_foreign_sales_stop_before_any_cost_or_profit_write(self):
  import sys
  sys.path.insert(0,str(a.CRM.parent/'telegram-bridge'))
  import allocation_runtime as r
  calls=[]
  class API:
   def _call(self,method,path):
    calls.append((method,path));return {'data':{'positions':[{'id':'1','price':{'currency':'USD','value':5},'sum':{'currency':'USD','value':10}}]}}
  with self.assertRaisesRegex(ValueError,'зафиксируйте'):r.sync_deal({'plan':{'targets':[]}},'1',API())
  self.assertEqual(calls,[('GET','/deal/1')])
