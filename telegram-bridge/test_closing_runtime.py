import unittest,tempfile,json,copy
from pathlib import Path
from unittest.mock import patch,Mock
from datetime import datetime
import closing_runtime as c
from closing_workflow import Registry
from closing_documents import validate_contract_rows
from closing_scheme import plan

class ClosingIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.reg=Registry(self.base/'jobs.json')
  self.patches=[patch.object(c,'REGISTRY',self.base/'jobs.json'),patch.object(c,'BASE',self.base),patch.object(c,'DB',self.base/'workflow.sqlite3'),patch.object(c,'CRM',self.base/'crm'),patch.object(c,'env',return_value={'TELEGRAM_CHAT_ID':'owner','EDO_NOTIFY_EMAIL':'a@example.test','SMTP_FROM':'b@example.test','SMTP_HOST':'mail.example.test','SMTP_PORT':'465','SMTP_USERNAME':'b','SMTP_PASSWORD':'secret'}),patch.object(c,'recipient',return_value='tanya')]
  for p in self.patches:p.start()
  c.CRM.mkdir()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
  self.tmp.cleanup()
 def job(self,mode='test',status='ready'):
  j=self.reg.enqueue('887',mode);docs=[]
  for i in range(3):
   p=self.base/f'{i}.pdf';p.write_bytes(b'%PDF-test');docs.append(str(p))
  return self.reg.patch(j['id'],status=status,fingerprint='fp',documents=docs,note='note',links=[],data={'payer_name':'Client','number':'Contract','payment':{'clause':'6.4.2'}})
 def test_import_real_interfaces(self):
  self.assertTrue(hasattr(c.WorkflowStore,'create'))
 def test_test_publish_never_writes_crm_or_archive(self):
  j=self.job()
  with patch.object(c,'api',side_effect=AssertionError('CRM write not allowed')):c.publish(j)
 def test_delivery_replay_no_duplicate_files_or_email(self):
  j=self.job();smtp=Mock();smtp.__enter__=Mock(return_value=smtp);smtp.__exit__=Mock(return_value=False);smtp.send_message.return_value={}
  with patch.object(c.smtplib,'SMTP_SSL',return_value=smtp),patch.object(c,'tg',return_value={'ok':True,'message_id':1}) as tg,patch.object(c,'send_file',return_value={'ok':True,'message_id':2}) as files:
   c.delivery(j);c.delivery(j)
   self.assertEqual(files.call_count,6);self.assertEqual(smtp.send_message.call_count,1);self.assertEqual(tg.call_count,3)
   self.assertEqual(self.reg.get(j['id'])['status'],'awaiting_test_review')
 def test_addendum_is_delivered_with_instructions_once(self):
  j=self.job('live');add=self.base/'Допсоглашение 887.pdf';add.write_bytes(b'%PDF-test')
  j=self.reg.patch(j['id'],additional_documents=[str(add)],note='ЭДО: ООО МК, ИНН 7733356410, договор 1.887')
  with patch.object(c,'send_email',return_value={'ok':True}) as email,patch.object(c,'tg',return_value={'ok':True,'message_id':1}),patch.object(c,'send_file',return_value={'ok':True,'message_id':2}) as files:
   c.delivery(j);c.delivery(j)
   self.assertEqual(email.call_count,1)
   message=email.call_args.args[0]
   self.assertEqual(message['To'],'a@example.test')
   self.assertIn(add.name,[a.get_filename() for a in message.iter_attachments()])
   self.assertIn('7733356410',message.get_body().get_content())
   self.assertEqual(sum(call.args[1]==str(add) for call in files.call_args_list),2)
 def test_owner_email_copy_is_separate_idempotent_effect(self):
  j=self.job('live');cfg=c.env();cfg['CLOSING_OWNER_EMAIL']='owner@example.test'
  with patch.object(c,'env',return_value=cfg),patch.object(c,'send_email',return_value={'ok':True}) as email,patch.object(c,'tg',return_value={'ok':True,'message_id':1}),patch.object(c,'send_file',return_value={'ok':True,'message_id':2}):
   c.delivery(j);c.delivery(j)
  self.assertEqual([x.args[0]['To'] for x in email.call_args_list],['a@example.test','owner@example.test'])
 def test_email_failure_does_not_hide_successful_telegram(self):
  j=self.job()
  with patch.object(c.smtplib,'SMTP_SSL',side_effect=TimeoutError),patch.object(c,'tg',return_value={'ok':True,'message_id':1}),patch.object(c,'send_file',return_value={'ok':True,'message_id':2}) as files:
   with self.assertRaises(ValueError):c.delivery(j)
   with self.assertRaises(ValueError):c.delivery(j)
   self.assertEqual(files.call_count,6)
 def test_real_telegram_callback_boolean_ack_then_prompt(self):
  j=self.job('live','awaiting_edo')
  query={'id':'q','from':{'id':'tanya'},'message':{'chat':{'id':'tanya'}},'data':'closing:'+j['id']+':sent'}
  import io
  responses=[io.BytesIO(json.dumps({'ok':True,'result':True}).encode()),io.BytesIO(json.dumps({'ok':True,'result':{'message_id':77}}).encode())]
  with patch.object(c,'env',return_value={'TELEGRAM_BOT_TOKEN':'test-token','TELEGRAM_CHAT_ID':'owner'}),patch.object(c.urllib.request,'urlopen',side_effect=responses) as transport,patch.object(c,'api',side_effect=AssertionError('No CRM write on button')):
   result=c.callback(query)
  self.assertEqual(result['message_id'],77)
  self.assertEqual(self.reg.get(j['id'])['pending_action'],'screenshot')
  self.assertEqual(self.reg.get(j['id'])['status'],'awaiting_edo')
  self.assertEqual(transport.call_count,2)
 def test_boolean_ack_for_unauthorized_callback(self):
  import io
  j=self.job('live','awaiting_edo')
  with patch.object(c,'env',return_value={'TELEGRAM_BOT_TOKEN':'test-token'}),patch.object(c.urllib.request,'urlopen',return_value=io.BytesIO(b'{"ok":true,"result":true}')):
   self.assertTrue(c.callback({'id':'q','from':{'id':'bad'},'message':{'chat':{'id':'bad'}},'data':'closing:'+j['id']+':sent'})['ok'])
  self.assertNotIn('pending_action',self.reg.get(j['id']))
 def test_foreign_callback_never_changes_state(self):
  j=self.job()
  with patch.object(c,'tg',return_value={'ok':True}):c.callback({'id':'q','from':{'id':'bad'},'message':{'chat':{'id':'bad'}},'data':'closing:'+j['id']+':review'})
  self.assertEqual(self.reg.get(j['id'])['status'],'ready')
 def test_repeated_test_review_notifies_once(self):
  j=self.job(status='awaiting_test_review');q={'id':'q','from':{'id':'tanya'},'message':{'chat':{'id':'tanya'}},'data':'closing:'+j['id']+':review'}
  with patch.object(c,'tg',return_value={'ok':True}) as tg:
   c.callback(q);c.callback(q)
   notices=[x for x in tg.call_args_list if x.args[1].get('chat_id')=='owner'];self.assertEqual(len(notices),1)
 def test_edo_confirmation_queued_without_blocking_polling(self):
  j=self.job('live','awaiting_edo');self.reg.patch(j['id'],pending_actor='tanya',pending_action='sent')
  with patch.object(c,'tg',return_value={'ok':True}),patch.object(c,'process',side_effect=AssertionError('Do not block polling')):
   self.assertTrue(c.message('tanya','ЭДО '+j['id']+'\nАкт: 1/12.10.2026\nУПД: 2/12.10.2026\nСчёт: 3/12.10.2026'))
  self.assertEqual(self.reg.get(j['id'])['status'],'edo_confirmed')
 def test_watcher_all_cached_deals_not_only_recent_twenty(self):
  path=c.CRM/'deal_browser_cache.json';data=[{'id':'887','program':{'id':'16'},'state':{'id':'135'}}]
  path.write_text(json.dumps(data));c.watch_cached();self.assertEqual(len(self.reg.read()['jobs']),0)
  data[0]['state']['id']='138';path.write_text(json.dumps(data));c.watch_cached();c.watch_cached();self.assertEqual(len(self.reg.read()['jobs']),1)
 def test_contract_line_wrap_with_numeric_columns(self):
  text='СПЕЦИФИКАЦИЯ\nНаружный блок Haier    шт.  1  1 000,00  1 000,00\nMODEL-X\nМонтаж    м  2  100,00  200,00\n'
  rows=[dict(name='Наружный блок Haier MODEL-X',quantity=1,total=1000),dict(name='Монтаж',quantity=2,total=200)]
  result=validate_contract_rows(text,rows);self.assertEqual(result[0]['unit'],'шт.');self.assertEqual(result[1]['unit_price'],'100.00')
  rows.reverse()
  self.assertEqual(validate_contract_rows(text,rows)[0]['unit_price'],'100.00')
  rows[0]['total']=201
  with self.assertRaises(ValueError):validate_contract_rows(text,rows)
 def test_workday_deadline(self):
  self.assertEqual(c.deadline('СПЕЦИФИКАЦИЯ 60 (шестьдесят) рабочих дней',[{'direction':'income','purpose':'по п.6.4.1','date':'23.09.2026'}]),'17.12.2026')
 def test_scheme_only_changes_reviewed_transitions(self):
  pairs=[('263','137','138'),('264','138','139'),('283','136','137'),('309','136','139'),('307','138','137'),('308','136','138'),('1','129','130')]
  original={'id':'16','states':[{'id':s} for s in ['136','137','138','139']],'transitions':[{'id':i,'from':{'id':a},'to':{'id':b}} for i,a,b in pairs]}
  before=copy.deepcopy(original);result=plan(original);self.assertEqual(original,before)
  self.assertEqual([x['id'] for x in result['states']],['136','138','137','139'])
  self.assertEqual({(t['from']['id'],t['to']['id']) for t in result['transitions']},{('136','138'),('138','137'),('137','139'),('129','130')})
 def test_renderer_uses_extracted_build_without_fuse(self):
  import document_renderer as r
  with patch.object(r,'BASE',self.base):
   executable=self.base/'extracted/squashfs-root/AppRun';executable.parent.mkdir(parents=True);executable.touch()
   env={};self.assertEqual(r.office_command(env),str(executable));self.assertNotIn('APPIMAGE_EXTRACT_AND_RUN',env)
 def test_renderer_fallback_extracts_without_fuse(self):
  import document_renderer as r
  with patch.object(r,'BASE',self.base):
   env={};self.assertTrue(r.office_command(env).endswith('LibreOffice.AppImage'));self.assertEqual(env['APPIMAGE_EXTRACT_AND_RUN'],'1')
 def test_changed_price_blocks_publication_before_upload(self):
  j=self.job('live');j.update(total_cents=100,data={'payer_id':'payer'})
  crm=Mock();crm._call.return_value={'data':{'payer':{'id':'payer'},'price':{'value':2}}}
  with patch.object(c,'api',return_value=crm):
   with self.assertRaisesRegex(ValueError,'сумма'):c.publish(j)
  crm.upload_file.assert_not_called()
 def test_payment_transition_requires_edo_confirmation(self):
  j=self.job('live');crm=Mock();crm._call.return_value={'data':{'state':{'id':'138'}}}
  with patch.object(c,'api',return_value=crm):
   with self.assertRaisesRegex(ValueError,'подтверждения'):c.transition(j,'137')
  self.assertTrue(all(call.args[0]=='GET' for call in crm._call.call_args_list))
 def test_complete_remote_transition_reconciled_without_second_write(self):
  j=self.job('live','awaiting_payment');j=self.reg.patch(j['id'],edo_confirmation={'actor':'tanya'},payer_inn='payer',seller_accounts=['our'],total_cents=100,data={'payer_id':'p'})
  deal={'id':'887','state':{'id':'139'},'price':{'value':1},'payer':{'id':'p'}}
  tx={'id':'a','date':'12.10.2026','document_number':'1','deal_id':'887','status':'assigned','counterparty_inn':'payer','account':'our','amount':1,'direction':'income'}
  crm=Mock();crm._call.return_value={'data':deal}
  with patch.object(c,'api',return_value=crm),patch.object(c,'sources',return_value=[tx]),patch.object(c,'transition',side_effect=AssertionError('Must not repeat completed transition')),patch.object(c,'tg',return_value={'ok':True,'message_id':5}):c.process(j['id'])
  self.assertEqual(self.reg.get(j['id'])['status'],'completed')
 def test_unchanged_bank_does_not_poll_crm_each_minute(self):
  j=self.job('live','awaiting_payment');j=self.reg.patch(j['id'],edo_confirmation={'actor':'tanya'},payer_inn='payer',seller_accounts=['our'],total_cents=100,data={'payer_id':'p'})
  crm=Mock();crm._call.return_value={'data':{'state':{'id':'137'},'price':{'value':1},'payer':{'id':'p'}}}
  with patch.object(c,'api',return_value=crm),patch.object(c,'sources',return_value=[]),patch.object(c,'tg',return_value={'ok':True}):
   c.process(j['id']);c.process(j['id']);self.assertEqual(crm._call.call_count,1)
 def test_invoice_create_has_fresh_fingerprint_and_replays_receipt(self):
  import contract_invoice
  j=self.job('live');j=self.reg.patch(j['id'],folder=str(self.base),data={'payer_id':'p','payment':{'clause':'6.4.2','fingerprint':'contract-fp','line':'Final','amount':1,'recipient_id':'s'}})
  fetched=self.base/'fetched.pdf';fetched.write_bytes(b'%PDF')
  with patch.object(contract_invoice,'list_invoices',return_value={'invoices':[]}),patch.object(contract_invoice,'create',return_value={'ok':True,'invoice_id':'123','invoice_number':'10'}) as create,patch.object(c.subprocess,'run',return_value=Mock(stdout=json.dumps({'ok':True,'path':str(fetched)}))):
   c.ensure_invoice(j,Mock());c.ensure_invoice(j,Mock())
   self.assertEqual(create.call_count,1);self.assertEqual(create.call_args.args[0]['expected_fingerprint'],'contract-fp')
 def test_live_publication_separate_crm_and_archive_receipts_no_repeats(self):
  import financial_archive
  j=self.job('live');crm=Mock();crm.upload_file.return_value={'id':'file'};crm._call.return_value={'data':{'id':'comment'}}
  with patch.object(c,'api',return_value=crm),patch.object(c,'validate_current',return_value={'state':{'id':'138'}}),patch.object(financial_archive,'archive_document',return_value={'ok':True,'onedrive_remote':'archive'}) as archive:
   c.publish(j);c.publish(j)
   self.assertEqual(crm.upload_file.call_count,3);self.assertEqual(archive.call_count,3)
   self.assertEqual(len(self.reg.get(j['id'])['receipts']),6)
 def test_pending_supplier_archive_keeps_crm_fallback_without_broken_link(self):
  (c.CRM/'financial_archive.json').write_text(json.dumps({'documents':[{'deal_id':'887','category':'supplier_closing','status':'pending','onedrive_remote':'missing','filename':'УПД.pdf'}]}))
  crm=Mock();crm.domain='example.test';crm._call.return_value={'data':[{'id':'f','name':'УПД.pdf','path':'/file.pdf'}]}
  with patch.object(c,'onedrive_url',side_effect=AssertionError('Do not use unconfirmed archive')):
   links=c.procurement_links('887',crm)
  self.assertEqual(len(links),1);self.assertEqual(links[0]['category'],'crm_document')
 def test_background_poll_uses_document_environment(self):
  with patch.object(c.subprocess,'run',return_value=Mock(returncode=0)) as run:
   c.poll_in_document_environment()
  args=run.call_args.args[0]
  self.assertTrue(args[0].endswith('/.report-venv/bin/python'))
  self.assertEqual(args[-1],'--poll')
  self.assertTrue(run.call_args.kwargs['check'])
 def test_revision_preview_is_not_sent_until_internal_release(self):
  j=self.job('live','ready');self.reg.patch(j['id'],manual_release_required=True)
  with patch.object(c,'publish',side_effect=AssertionError('Must inspect revision before publication')):
   c.process(j['id'])
  self.assertEqual(self.reg.get(j['id'])['status'],'ready')
if __name__=='__main__':unittest.main()

class EdoScreenshotTests(unittest.TestCase):
 tearDown=ClosingIntegrationTests.tearDown
 def setUp(self):
  ClosingIntegrationTests.setUp(self)
  self.out=patch.object(c,'OUT',self.base/'bundles');self.out.start();self.addCleanup(self.out.stop)
 def pending(self,deal='887'):
  j=self.reg.enqueue(deal,'live')
  return self.reg.patch(j['id'],status='awaiting_edo',pending_actor='tanya',pending_action='screenshot',screenshot_prompt_id=100 if deal=='887' else 200)
 def upload(self,reply=100):
  return {'chat':{'id':'tanya'},'from':{'id':'tanya'},'message_id':300,'photo':[{'file_id':'image'}],'reply_to_message':{'message_id':reply}}
 def downloader(self,msg):
  p=self.base/'shot.png';p.write_bytes(b'\x89PNG\r\n\x1a\nfixture');return str(p),None
 def test_screenshot_is_durable_before_transition_and_duplicate_is_safe(self):
  j=self.pending()
  with patch.object(c,'tg',return_value={'ok':True}):
   self.assertTrue(c.screenshot(self.upload(),self.downloader))
   self.assertTrue(c.screenshot(self.upload(),Mock(side_effect=AssertionError('No repeat download'))))
  saved=self.reg.get(j['id']);self.assertEqual(saved['status'],'edo_evidence_pending');self.assertNotIn('edo_confirmation',saved)
  self.assertTrue(Path(saved['edo_evidence']['path']).exists())
 def test_two_deals_reply_routes_exact_job(self):
  a=self.pending();b=self.pending('894')
  with patch.object(c,'tg',return_value={'ok':True}):c.screenshot(self.upload(200),self.downloader)
  self.assertEqual(self.reg.get(a['id'])['status'],'awaiting_edo');self.assertEqual(self.reg.get(b['id'])['status'],'edo_evidence_pending')
 def test_ambiguous_or_foreign_reply_cannot_confirm(self):
  self.pending();self.pending('894');msg=self.upload();msg.pop('reply_to_message')
  with self.assertRaises(ValueError):c.screenshot(msg,Mock(side_effect=AssertionError('Must not download')))
  with self.assertRaises(ValueError):c.screenshot(self.upload(999),Mock())
 def test_unauthorized_image_and_download_failure_never_confirm(self):
  j=self.pending();m=self.upload();m['from']['id']='other';self.assertFalse(c.screenshot(m,Mock()))
  with self.assertRaises(ValueError):c.screenshot(self.upload(),lambda m:(None,'download failed'))
  self.assertEqual(self.reg.get(j['id'])['status'],'awaiting_edo')
 def test_archive_failure_preserves_crm_receipt_without_confirmation(self):
  j=self.pending()
  with patch.object(c,'tg',return_value={'ok':True}):c.screenshot(self.upload(),self.downloader)
  j=self.reg.get(j['id']);api=Mock();api.upload_file.return_value={'id':'file'};api._call.return_value={'data':{'id':'comment'}}
  with patch.object(c,'api',return_value=api),patch.object(c,'validate_current'),patch('financial_archive.archive_document',side_effect=TimeoutError):
   with self.assertRaises(ValueError):c.preserve_edo_evidence(j)
   with self.assertRaises(ValueError):c.preserve_edo_evidence(j)
  self.assertEqual(api.upload_file.call_count,1)
  self.assertNotIn('edo_confirmation',self.reg.get(j['id']))
 def test_success_requires_both_remote_receipts(self):
  j=self.pending()
  with patch.object(c,'tg',return_value={'ok':True}):c.screenshot(self.upload(),self.downloader)
  api=Mock();api.upload_file.return_value={'id':'file'};api._call.return_value={'data':{'id':'comment'}}
  with patch.object(c,'api',return_value=api),patch.object(c,'validate_current'),patch('financial_archive.archive_document',return_value={'ok':True}):
   result=c.preserve_edo_evidence(self.reg.get(j['id']))
  self.assertEqual(result['status'],'edo_confirmed');self.assertEqual(result['edo_confirmation']['actor'],'tanya')
