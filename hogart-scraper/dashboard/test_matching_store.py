import tempfile,unittest
from pathlib import Path
from matching_store import candidate,project,decide,claim,finish,connection
class MatchingStoreTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.db=Path(self.tmp.name)/'match.db'
  self.key,self.payload=candidate('861',{'id':'1','name':'Корпус RAM','quantity':2,'unit':'шт'},{'source_name':'DKC корпус RAM','qty_used':2},{'id':'invoice'})
  self.inputs={self.key:self.payload}
 def test_threshold_and_cache(self):
  for confidence,expected in [(70,'review'),(71,'auto')]:
   with connection(self.db) as db:db.execute('DELETE FROM decisions')
   project(self.inputs,self.db);self.assertEqual(len(claim(self.db)),1)
   finish(self.key,{'same':True,'confidence':confidence,'reason':'Совпадает модель','conflicts':[]},self.db)
   self.assertEqual(project(self.inputs,self.db)[self.key]['state'],expected);self.assertEqual(claim(self.db),[])
 def test_human_wins_and_rejection_persists(self):
  project(self.inputs,self.db);claim(self.db);decide(self.key,'rejected',77,self.inputs,self.db)
  finish(self.key,{'same':True,'confidence':99,'reason':'Да','conflicts':[]},self.db)
  self.assertEqual(project(self.inputs,self.db)[self.key]['state'],'rejected');self.assertEqual(claim(self.db),[])
 def test_stale_and_invalid(self):
  with self.assertRaises(ValueError):decide(self.key,'accepted',77,{},self.db)
  project(self.inputs,self.db);claim(self.db)
  for value in [True,float('nan'),101]:
   with self.assertRaises(ValueError):finish(self.key,{'confidence':value},self.db)
 def test_conflicts_never_auto(self):
  project(self.inputs,self.db);claim(self.db);finish(self.key,{'same':True,'confidence':99,'reason':'Но есть отличие','conflicts':['цвет']},self.db)
  self.assertEqual(project(self.inputs,self.db)[self.key]['state'],'review')
 def test_deterministic_veto(self):
  key,payload=candidate('861',{'id':'1','name':'ABB S201 C10'},{'source_name':'ABB S201 C16'},{'id':'i'});inputs={key:payload}
  self.assertEqual(project(inputs,self.db)[key]['state'],'blocked');self.assertEqual(claim(self.db),[])
  with self.assertRaises(ValueError):decide(key,'accepted',77,inputs,self.db)
 def test_ai_does_not_fill_missing_quantity(self):
  from shipment_procurement import coverage
  row={'id':'1','name':'Корпус RAM','quantity':2,'unit':'шт'};line={'offer_row_id':'1','source_name':'DKC корпус RAM','qty_used':1}
  inv={'id':'i','allocations':[{'deal_id':'861','source_lines':[line]}]}
  reg={'deals':{'861':{'items':[{'offer_row_id':'1','name':row['name'],'qty':2,'unit':'шт','actual_qty':1}]}},'invoices':[inv]}
  key,_=candidate('861',row,line,inv)
  result=coverage('861',[row],reg,{key:{'state':'auto','confidence':99}})['1']
  self.assertEqual(result['state'],'attention');self.assertIn('Не хватает',result['reason'])
 def test_shared_invoice_quantity_cannot_be_reused(self):
  from shipment_procurement import coverage
  row={'id':'1','name':'Товар','quantity':2,'unit':'шт'};line={'key':'sku','offer_row_id':'1','source_name':'Товар','source_qty':2,'qty_used':2}
  reg={'deals':{'861':{'items':[{'offer_row_id':'1','name':'Товар','qty':2,'unit':'шт','actual_qty':2}]}},'invoices':[{'id':'i','allocations':[{'deal_id':'861','source_lines':[line]},{'deal_id':'999','source_lines':[line]}]}]}
  result=coverage('861',[row],reg)['1'];self.assertEqual(result['state'],'attention');self.assertIn('сверх',result['reason'])
 def test_human_can_resolve_ai_uncertainty_but_not_rule_veto(self):
  project(self.inputs,self.db);claim(self.db)
  finish(self.key,{'same':False,'confidence':60,'reason':'Не указан производитель','conflicts':['Производитель не указан в сделке']},self.db)
  decide(self.key,'accepted',77,self.inputs,self.db)
  self.assertEqual(project(self.inputs,self.db)[self.key]['state'],'accepted')
 def test_format_upgrade_preserves_human_rejection_without_new_ai_call(self):
  import json,hashlib,time
  old={**self.payload,'version':'rules-1'};key=hashlib.sha256(json.dumps(old,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  with connection(self.db) as db:db.execute('INSERT INTO decisions(id,payload,state,result,updated) VALUES(?,?,?,?,?)',(key,json.dumps(old),'rejected',json.dumps({'reason':'Решение владельца'}),time.time()))
  self.assertEqual(project(self.inputs,self.db)[self.key]['state'],'rejected');self.assertEqual(claim(self.db),[])
 def test_format_upgrade_rechecks_previously_false_conflict(self):
  import json,hashlib,time
  old={**self.payload,'version':'rules-1'};key=hashlib.sha256(json.dumps(old,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  with connection(self.db) as db:db.execute('INSERT INTO decisions(id,payload,state,result,updated) VALUES(?,?,?,?,?)',(key,json.dumps(old),'blocked',json.dumps({'reason':'Старая нормализация'}),time.time()))
  self.assertEqual(project(self.inputs,self.db)[self.key]['state'],'queued')
