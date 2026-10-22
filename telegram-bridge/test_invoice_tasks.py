import tempfile,unittest,time,json
from pathlib import Path
from unittest.mock import patch,Mock
import invoice_tasks as tasks
import invoice_continuation as continuation
import bridge

class InvoiceTaskTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);p=patch.object(tasks,'STORE',self.root/'tasks.json');p.start();self.addCleanup(p.stop)
 def add(self,number,message):
  p=self.root/(number+'.pdf');p.write_bytes(number.encode())
  text=f'Счет-договор на оплату № ЭК00-{number} от 12 мая 2026 г.\nИНН 7720298746\nИНН 7743926877\nИтого: 99794,70'
  return tasks.register('owner',p,text,message)
 def test_two_files_cancel_second_survives_reload_keeps_first(self):
  self.add('054832',2843);self.add('054835',2845)
  state=tasks.read('owner');self.assertEqual('ЭК00-054832',tasks.active(state)['number'])
  state,result=tasks.cancel('owner','счет 054835 - не обрабатывай',2850)
  self.assertEqual(1,len(result['cancelled']))
  state=tasks.read('owner');self.assertEqual('cancelled',state['documents'][1]['status'])
  self.assertEqual('ЭК00-054832',tasks.active(state)['number'])
  prompt=tasks.prompt(state);self.assertNotIn('ЭК00-054835',prompt)
 def test_out_of_order_download_cannot_revive_cancelled_invoice(self):
  self.add('054832',2843);tasks.cancel('owner','счет 054835 - не обрабатывай',2850)
  state,doc=self.add('054835',2845);self.assertEqual('cancelled',doc['status'])
  self.assertEqual('ЭК00-054832',tasks.active(state)['number'])
 def test_duplicates_and_chat_isolation(self):
  self.add('054832',2843);self.add('054832',2844)
  self.assertEqual(1,len(tasks.read('owner')['documents']))
  tasks.cancel('other','счет 054832 - не обрабатывай',2850)
  self.assertEqual('pending',tasks.read('owner')['documents'][0]['status'])
 def test_bare_no_does_not_cancel_a_queue(self):
  self.add('054832',2843)
  self.assertIsNone(tasks.cancel('owner','нет',2850))
  self.assertEqual('pending',tasks.active(tasks.read('owner'))['status'])
 def test_cancel_handler_is_deterministic_and_removes_preview(self):
  self.add('054832',2843);self.add('054835',2845)
  preview={'invoice':{'number':'ЭК00-054835'}}
  with patch.object(bridge.statement_document_context,'exclude_documents'),patch.object(bridge,'current_deal_ui_state',return_value={'supplier_invoice_preview':preview,'supplier_invoice_queue':[preview]}),patch.object(bridge,'update_deal_ui_state') as update,patch.object(bridge,'send_message') as send,patch.object(bridge,'ask_claude') as model,patch.object(bridge,'hogart_live_search') as catalog:
   self.assertTrue(bridge.handle_invoice_cancellation('fake','owner',{'text':'счет 054835 - не обрабатывай','message_id':2850}))
   model.assert_not_called();catalog.assert_not_called()
   self.assertIn('Продолжаем счёт №ЭК00-054832',send.call_args.args[2])
   self.assertEqual([],update.call_args.kwargs['supplier_invoice_queue'])
 def test_forbidden_protocol_cannot_trigger_catalog_or_other_write(self):
  state,doc=self.add('054832',2843)
  for response in ['HOGART_SEARCH: Haier','CREATE_MEGAPLAN_DEAL_BEGIN\n{}\nCREATE_MEGAPLAN_DEAL_END','ATTACH_FILE: /tmp/unrelated']:
   self.assertEqual(tasks.question(doc),tasks.guard_reply(response,doc))
  self.assertEqual('DEAL_LEDGER_REQUEST: 861',tasks.guard_reply('DEAL_LEDGER_REQUEST: 861',doc))
 def test_deal_binding_supports_invoice_contract(self):
  state,doc=self.add('054832',2843)
  spec={'deal_id':'861','invoice':{'number':'ЭК00-054832','supplier_inn':'7720298746','buyer_inn':'7743926877'}}
  self.assertIsNotNone(continuation.bind(spec,doc,'owner'))
 def test_old_catalog_context_cannot_make_current_message_a_search(self):
  self.assertFalse(bridge.needs_fresh_hogart_search('к существующей'))
  self.assertFalse(bridge.needs_fresh_hogart_search('счет 054835 - не обрабатывай'))
  self.assertTrue(bridge.needs_fresh_hogart_search('Найди цену Haier Flexis25'))
 def test_upload_on_procurement_menu_does_not_inherit_its_last_deal(self):
  self.assertTrue(tasks.accepts_upload({'pending':'procurement_menu','current_deal_id':'894'}))
  self.assertFalse(tasks.accepts_upload({'pending':'invoice_file','supplier_invoice_deal_id':'894'}))
  self.assertFalse(tasks.accepts_upload({'deal_creation_active':True}))
 def test_service_path_is_not_a_new_catalog_request(self):
  raw='счет 054835 - не обрабатывай'
  enriched=raw+'\nsource_path=/home/user/hogart-scraper/incoming/invoice.pdf; закупка27600'
  self.assertTrue(bridge.needs_fresh_hogart_search(enriched))  # Exact old failure.
  self.assertFalse(bridge.explicit_catalog_request(raw))
 def test_complete_advances_queue_without_reviving_cancelled(self):
  self.add('054832',2843);self.add('054835',2845)
  state=tasks.read('owner');tasks.complete('owner',state['documents'][0]['path'])
  self.assertEqual('ЭК00-054835',tasks.active(tasks.read('owner'))['number'])
if __name__=='__main__':unittest.main()
