import unittest,tempfile,time
from pathlib import Path
from unittest.mock import patch
import invoice_tasks as tasks
import catalog_conversation as routing
import bridge
class RoutingTests(unittest.TestCase):
 def setUp(self):
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name);p=patch.object(tasks,'STORE',self.root/'tasks.json');p.start();self.addCleanup(p.stop)
 def test_exact_screenshot_sequence_keeps_catalog_and_invoice(self):
  p=self.root/'invoice.pdf';p.write_bytes(b'invoice');tasks.register('owner',p,'Счет на оплату №054832',1)
  first='Найди самые дешевые кондиционеры в наличии: хайер на 7 кВт, 2 штуки, и на 3,5 кВт, 1 штуку. Пришли стоимость закупки и розничная'
  self.assertTrue(bridge.explicit_catalog_request(first));state=routing.begin('owner',first);routing.finish('owner','Haier: инверторные модели')
  for text in ['А посмотри не инверторные модели','Найди самые дешевые неинверторные кондиционеры в наличии: две штуки на 7 кВт и одну штуку на 3,5 кВт. Выведи сюда название, закупку и розницу']:
   state=tasks.read('owner');self.assertTrue(routing.is_turn(text,state));state=routing.begin('owner',text);self.assertIsNone(tasks.active(state));prompt=routing.prompt(state);self.assertNotIn('054832',prompt);self.assertIn('7 кВт',prompt);self.assertIn('хайер',prompt)
  self.assertEqual('pending',tasks.read('owner')['documents'][0]['status'])
 def test_generic_catalog_without_brand(self):
  self.assertTrue(routing.explicit('Найди самые дешевые неинверторные кондиционеры в наличии'))
  self.assertFalse(routing.explicit('счет054835 не обрабатывай'))
  self.assertFalse(routing.is_turn('Отнести счет к сделке861',{'foreground':'catalog','catalog_at':time.time()}))
 def test_new_upload_restores_invoice_flow(self):
  routing.begin('owner','Найди кондиционеры');p=self.root/'other.pdf';p.write_bytes(b'new');state,doc=tasks.register('owner',p,'Счет на оплату №4772',5)
  self.assertEqual('invoice',state['foreground']);self.assertEqual('4772',tasks.active(state)['number'])
 def test_catalog_cannot_write_finances(self):
  self.assertNotIn('SUPPLIER_INVOICE_APPLY',routing.guard('SUPPLIER_INVOICE_APPLY_BEGIN\n{}\nSUPPLIER_INVOICE_APPLY_END'))
  self.assertEqual('HOGART_SEARCH: Haier HSU',routing.guard('HOGART_SEARCH: Haier HSU'))
 def test_unrelated_chat_and_expiry(self):
  routing.begin('one','Найди кондиционеры');self.assertFalse(routing.is_turn('А посмотри другие',tasks.read('two')))
  self.assertFalse(routing.is_turn('А посмотри другие',{'foreground':'catalog','catalog_at':time.time()-90000}))
 def test_proposal_with_stock_search_can_build_documents(self):
  raw='Подготовь КП и экономику для Алексея на кондиционеры в наличии одного бренда: 2,5 кВт - 2 шт, 7,0 кВт - 1 шт. с монтажом, дополнительная трасса для 2,5 кВт - 38 м суммарно, для 7,0 кВт - 14 м'
  self.assertTrue(routing.is_turn(raw,{}))
  state=routing.begin('owner',raw)
  reply='BUILD_KP_BEGIN\n{}\nBUILD_KP_END'
  self.assertEqual(reply,routing.guard(reply,state))
  self.assertIn(raw,routing.prompt(state))
  self.assertIn('после свежего поиска',routing.prompt(state))
  self.assertNotIn('SUPPLIER_INVOICE_APPLY',routing.guard('SUPPLIER_INVOICE_APPLY_BEGIN\n{}\nSUPPLIER_INVOICE_APPLY_END',state))
  state=routing.begin('owner','Только инверторные')
  self.assertEqual(reply,routing.guard(reply,state))
 def test_plain_catalog_does_not_authorize_proposal(self):
  state=routing.begin('owner','Найди кондиционеры в наличии')
  routing.finish('owner','Можно подготовить КП')
  self.assertNotIn('BUILD_KP',routing.guard('BUILD_KP_BEGIN\n{}\nBUILD_KP_END',tasks.read('owner')))

class ActualRoutingBlockTests(RoutingTests):
 def test_alexey_kentatsu_tolerance_stays_in_current_task(self):
  from unittest.mock import Mock
  import textwrap
  source=Path(bridge.__file__).read_text();start=source.index('        routing_text =');end=source.index('        catalog_steps =',start)
  block=compile(textwrap.dedent(source[start:end]),'<actual bridge routing>','exec')
  for raw in ['Подготовь КП и экономику для Алексея на самые дешевые не инверторные кондиционеры в наличии одного бренда: 2,5 кВт - 2 шт, 7,0 кВт - 1 шт. с монтажом, дополнительная трасса 38 м и 14 м', 'А посмотри кондиционеры Kentatsu', 'Увеличить допуск по мощности', 'Да', 'До 0,5 кВт']:
   ns={'msg':{'text':raw},'chat_id':'owner','is_owner':True,'supplier_invoice_mode':False,'creation_document_mode':False,'text':raw,'invoice_tasks':tasks,'catalog_conversation':routing,'explicit_catalog_request':bridge.explicit_catalog_request,'statement_document_context':Mock(),'invoice_continuation':Mock(),'current_deal_ui_state':Mock(return_value={})}
   exec(block,ns)
   self.assertTrue(ns['catalog_task_mode'],raw)
   self.assertIn('Алексея',ns['text'])
   self.assertNotIn('Николай',ns['text'])
   if raw not in ('А посмотри кондиционеры Kentatsu',) and raw != 'Подготовь КП и экономику для Алексея на самые дешевые не инверторные кондиционеры в наличии одного бренда: 2,5 кВт - 2 шт, 7,0 кВт - 1 шт. с монтажом, дополнительная трасса 38 м и 14 м':
    self.assertIn('Kentatsu',ns['text'])
   routing.finish('owner','Уточните допуск по мощности')
  for _ in range(10):
   routing.begin('owner','Да');routing.finish('owner','Уточнение принято')
  state=tasks.read('owner')
  self.assertIn('Алексея',routing.prompt(state))
  self.assertIn('Kentatsu',routing.prompt(state))
  self.assertTrue(routing.proposal_requested(state))

 def test_failed_supplier_search_does_not_call_model_as_empty_stock(self):
  from unittest.mock import Mock
  import textwrap
  source=Path(bridge.__file__).read_text()
  for supplier in ['hogart','daichi']:
   start=source.index('        def run_'+supplier+'_search_round(')
   end=source.index('        def run_daichi_search_round(',start) if supplier=='hogart' else source.index('        # Safety net',start)
   model=Mock(return_value='unexpected model response')
   filters=['Kentatsu'] if supplier=='hogart' else [{'keyword':'Kentatsu'}]
   ns={'extract_'+supplier+'_searches':Mock(return_value=('',filters)),supplier+'_live_search':Mock(return_value=None),'ask_current_model':model,'send_typing':Mock(),'token':'test','chat_id':'owner','catalog_conversation':routing,'LOG_PREFIX':'test'}
   exec(compile(textwrap.dedent(source[start:end]),'<actual supplier search>','exec'),ns)
   reply,fired=ns['run_'+supplier+'_search_round']('search')
   self.assertTrue(fired);self.assertIn('Наличие и цены не подтверждены',reply)
   model.assert_not_called()
  self.assertIsNone(routing.search_failure('Daichi',[{'count':0,'items':[]}]))

 def test_handler_does_not_inject_old_invoice_into_followup(self):
  from unittest.mock import Mock
  source=Path(bridge.__file__).read_text();start=source.index('        routing_text =');end=source.index('        catalog_steps =',start)
  import textwrap
  block=compile(textwrap.dedent(source[start:end]),'<actual bridge routing>','exec')
  p=self.root/'bill.pdf';p.write_bytes(b'old');tasks.register('owner',p,'Счет на оплату №054832',1)
  for raw in ['Найди самые дешевые кондиционеры Haier на7кВт2шт и3,5кВт1шт','А посмотри не инверторные модели']:
   context=Mock();ns={'msg':{'text':raw},'chat_id':'owner','is_owner':True,'supplier_invoice_mode':False,'creation_document_mode':False,'text':raw,'invoice_tasks':tasks,'catalog_conversation':routing,'explicit_catalog_request':bridge.explicit_catalog_request,'statement_document_context':context,'invoice_continuation':Mock(),'current_deal_ui_state':Mock(return_value={})}
   exec(block,ns);self.assertTrue(ns['catalog_task_mode']);self.assertFalse(ns['invoice_task_mode']);context.recent_context.assert_not_called();self.assertNotIn('054832',ns['text']);self.assertIn('Haier',ns['text'])
