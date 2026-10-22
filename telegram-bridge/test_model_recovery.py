import json,tempfile,unittest,subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bridge,model_recovery,statement_document_context as context
class ModelRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.session=self.root/'session';self.session.write_text('stale-thread')
  self.patches=[patch.object(bridge,'SESSION_FILE',str(self.session)),patch.object(bridge,'MODEL_FAILURES_FILE',str(self.root/'failures.json')),patch.object(bridge,'UI_CONTEXT',SimpleNamespace(chat_id='owner'))]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.temp.cleanup()
 def result(self,error=None,code=0):
  return subprocess.CompletedProcess([],code,stdout=json.dumps({'type':'turn.failed','error':{'message':error}}) if error else '\n'.join([json.dumps({'type':'thread.started','thread_id':'new-thread'}),json.dumps({'type':'item.completed','item':{'type':'agent_message','text':'Готов ответ'}})]),stderr='')
 def test_auth_does_not_spawn_repeated_threads_and_preserves_request(self):
  with patch.object(bridge,'_run_codex',return_value=self.result('refresh token was already used',1)) as run:
   out=bridge.ask_claude('', 'Разобрать сохранённый файл')
  self.assertEqual(run.call_count,1);self.assertIsInstance(out,model_recovery.ModelUnavailable);self.assertIn('повторно отправлять не нужно',out)
  self.assertEqual(model_recovery.latest(bridge.MODEL_FAILURES_FILE,'owner')['prompt'],'Разобрать сохранённый файл');self.assertIsNone(model_recovery.latest(bridge.MODEL_FAILURES_FILE,'other'))
 def test_missing_rollout_retries_and_keeps_new_thread(self):
  with patch.object(bridge,'_run_codex',side_effect=[self.result('no rollout found for thread id',1),self.result()]) as run:self.assertEqual(bridge.ask_claude('','test'),'Готов ответ')
  self.assertEqual(run.call_args_list[1].args[0],'');self.assertEqual(self.session.read_text(),'new-thread')
 def test_zero_exit_failed_turn_is_not_success(self):
  with patch.object(bridge,'_run_codex',return_value=self.result('refresh token was already used',0)):self.assertIsInstance(bridge.ask_fresh_document_model('file'),model_recovery.ModelUnavailable)
 def test_timeout_keeps_prompt_and_retry_marks_answered(self):
  with patch.object(bridge,'_run_codex',side_effect=subprocess.TimeoutExpired('codex',300)):out=bridge.ask_claude('','original')
  self.assertNotIn('короче',out)
  with patch.object(bridge,'_run_codex',return_value=self.result()):bridge.ask_claude('','original')
  self.assertIsNone(model_recovery.latest(bridge.MODEL_FAILURES_FILE,'owner'))
 def test_compaction_never_drops_retryable_requests(self):
  data={f'done-{i}':{'status':'model_answered','updated_at':i} for i in range(50)}
  data['retry']={'status':'needs_retry','updated_at':0}
  compact=model_recovery.compact(data)
  self.assertIn('retry',compact);self.assertEqual(20,sum(x['status']=='model_answered' for x in compact.values()))
class StatementDocumentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);(self.root/'evidence/finish_all').mkdir(parents=True);(self.root/'reports').mkdir();self.file=self.root/'invoice.pdf';self.file.write_bytes(b'fixture')
  (self.root/'data').mkdir()
  (self.root/'data/review_registry.json').write_text(json.dumps({'tasks':{},'historical_answers':[{'number':30,'invoices':'11-197','supplier':'АРТ ТЕХНОЛОГИЯ','bank_ids':['b'],'amount_cents':39803720}]}))
  (self.root/'reports/ledger.json').write_text(json.dumps([{'id':'b','inn':'7709895139','company':'КЛИВЭЛ'}]))
  self.text='Счет на оплату № 11-197 от 24 июня. ИНН7709895139 покупатель ИНН7743151323 Итого:398 037,20'
 def tearDown(self):self.tmp.cleanup()
 def test_invoice_matches_without_model_and_duplicate_is_one_entry(self):
  for _ in range(2):r=context.match_document(self.file,self.text,'owner',self.root)
  self.assertEqual(r['old_question'],30);self.assertEqual(r['status'],'document_received_not_posted');self.assertIn('НЕ спрашивай',context.prompt_context(r));self.assertEqual(len(json.loads((self.root/'evidence/telegram_intake/manifest.json').read_text())),1)
 def test_amount_difference_is_retained_but_not_declared_exact(self):
  r=context.match_document(self.file,self.text.replace('398 037,20','18 000,00'),'owner',self.root)
  self.assertEqual(r['amount_relation'],'amount_differs');self.assertEqual(r['document_amount_cents'],1800000);self.assertEqual(r['amount_cents'],39803720)
 def test_offer_invoice_number_is_recognized(self):
  r=context.match_document(self.file,self.text.replace('Счет на','Счет-оферта на'),'owner',self.root)
  self.assertEqual(r['invoice'],'11-197')
 def test_wrong_buyer_amount_or_supplier_does_not_match(self):
  for a,b in [('7743151323','7743926877'),('7709895139','7709895130')]:self.assertIsNone(context.match_document(self.file,self.text.replace(a,b),'owner',self.root))

class FailedLedgerTests(unittest.TestCase):
 def setUp(self):bridge.DEAL_LEDGER_CACHE.clear()
 def test_timeout_with_empty_local_cache_is_unknown_not_empty(self):
  with patch.object(bridge,'_run_deal_ledger_cli',return_value=[]),patch.object(bridge.subprocess,'run',side_effect=subprocess.TimeoutExpired('crm',45)),patch.object(bridge,'record_operation_timing'):
   self.assertIsNone(bridge.fetch_deal_ledger('856'))
 def test_timeout_with_old_rows_also_cannot_authorize_changes(self):
  with patch.object(bridge,'_run_deal_ledger_cli',return_value=[{'name':'old'}]),patch.object(bridge.subprocess,'run',side_effect=subprocess.TimeoutExpired('crm',45)),patch.object(bridge,'record_operation_timing'):
   self.assertIsNone(bridge.fetch_deal_ledger('856'))
 def test_verified_empty_live_deal_is_empty(self):
  result=subprocess.CompletedProcess([],0,json.dumps({'ok':True,'ledger':[]}), '')
  with patch.object(bridge.subprocess,'run',return_value=result),patch.object(bridge,'record_operation_timing'):
   self.assertEqual(bridge.fetch_deal_ledger('856'),[])
 def test_missing_ledger_in_response_is_unknown(self):
  result=subprocess.CompletedProcess([],0,json.dumps({'ok':True}), '')
  with patch.object(bridge.subprocess,'run',return_value=result),patch.object(bridge,'record_operation_timing'):
   self.assertIsNone(bridge.fetch_deal_ledger('856'))
