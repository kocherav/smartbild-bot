import ast,json,unittest
from pathlib import Path
from unittest.mock import Mock
import creation_attachment as route

REQUEST='Используя светильники из данного счёта создай сделку с клиентом Jet car. Мне нужен договор и счёт на 100 процентную оплату. В сделке цена для клиента 42120 за 1 шт'
TODAY_REQUEST=('Создай по этому счёту новую сделку для JetCar. В сделку включи только '
               'светильники. Закупочную цену возьми из счёта. Продажную цену я пока не указал.')

class CreationAttachmentTests(unittest.TestCase):
 def test_saved_instruction(self):
  s=route.initial_state(REQUEST)
  self.assertEqual(s['deal_create_spec']['client_name'],'Jet car')
  self.assertEqual(s['deal_creation_request'],REQUEST)
  self.assertIsNone(s['deal_creation_result'])
  self.assertTrue(route.awaiting_file(REQUEST))
 def test_natural_invoice_words_between_create_and_deal_start_fresh_flow(self):
  self.assertTrue(route.explicit(TODAY_REQUEST))
  state=route.initial_state(TODAY_REQUEST)
  self.assertEqual(state['deal_creation_request'],TODAY_REQUEST)
  self.assertEqual(state['deal_create_spec']['client_name'],'JetCar')
  self.assertNotIn('items',state['deal_create_spec'])
 def test_fresh_prompt_after_restart(self):
  s=json.loads(json.dumps(route.initial_state(REQUEST)))
  p=route.prompt(s,'current.pdf','СЧЕТ ЦС00-196669; Покупатель ИНСИС; LOCUS 18 шт 39780')
  for part in ['Jet car','42120','100 процентную','current.pdf','LOCUS 18 шт 39780']:self.assertIn(part,p)
  self.assertNotIn('890',p)
 def test_scan_and_caption(self):
  self.assertIn('Прочитай именно текущий файл',route.prompt(route.initial_state(REQUEST),'scan.pdf',''))
  self.assertTrue(route.explicit(REQUEST))
  self.assertTrue(route.explicit('Создайте новую сделку с клиентом ООО А'))
  self.assertFalse(route.explicit('пришли карточку ИП Кочержинский'))
 def test_late_document_reply_cannot_overwrite_new_creation_request(self):
  old=route.initial_state(REQUEST)
  old['deal_creation_source_path']='old.pdf'
  new_text=('Создай по этому счёту новую сделку для JetCar. В сделку включи только '
            'светильники. Продажную цену я пока не указал — спроси её у меня.')
  current=route.initial_state(new_text)
  current['deal_creation_source_path']='current.pdf'
  self.assertTrue(route.is_current(current,new_text,'current.pdf'))
  self.assertFalse(route.is_current(current,old['deal_creation_request'],'old.pdf'))
 def test_real_message_entry_separate_text(self):
  tree=ast.parse(Path(__file__).with_name('bridge.py').read_text())
  node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='process_business_message')
  human_handler=Mock(return_value=True)
  ns={'current_deal_ui_state':lambda chat:{},'order_continuation':__import__('order_continuation'),'creation_attachment':route,'update_deal_ui_state':Mock(),'invoice_tasks':Mock(),'send_message':Mock(),'token':'test','send_document':Mock(),'handle_human_workflow':human_handler}
  exec(compile(ast.Module(body=[node],type_ignores=[]),'bridge-entry','exec'),ns)
  ns['process_business_message']({'text':REQUEST},'owner',True,False)
  human_handler.assert_called_once_with('test','owner',REQUEST)
  ns['update_deal_ui_state'].assert_not_called()
 def test_file_entry_extracts_and_followups_stay_isolated(self):
  text=Path(__file__).with_name('bridge.py').read_text()
  self.assertIn('text += creation_attachment.prompt(current_deal_ui_state(chat_id), source_document_path, extracted_creation)',text)
  self.assertIn('if creation_document_mode:\n                return ask_fresh_document_model(text +',text)
  self.assertIn('discarded stale deal-creation document reply',text)
 def test_named_client_search_before_review(self):
  tree=ast.parse(Path(__file__).with_name('bridge.py').read_text())
  node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='prepare_deal_creation_review')
  ns={'search_creation_clients':Mock(return_value={'ok':True,'clients':[{'id':'42','name':'JetCar','kind':'company'}]}),'update_deal_ui_state':Mock(),'send_message':Mock(),'deal_creation':Mock(),'DEAL_CREATE_REVIEW_KEYBOARD':{},'PAYER_UPLOAD_KEYBOARD':{}}
  # Stop at actual review boundary; asserts selected existing ID before any CRM action.
  ns['deal_creation'].review.side_effect=ValueError('test boundary')
  exec(compile(ast.Module(body=[node],type_ignores=[]),'review','exec'),ns)
  ns['prepare_deal_creation_review']('token','owner',{'client_name':'Jet car','user_request':REQUEST})
  ns['search_creation_clients'].assert_called_once_with('Jet car')
  self.assertEqual(ns['deal_creation'].review.call_args.args[0]['client_id'],'42')
