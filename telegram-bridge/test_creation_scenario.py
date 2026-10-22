from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import bridge


class CreationScenarioTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        patched = patch.multiple(bridge, RUNTIME_ACTIVE=True, UI_CONTEXT=None,
            DEAL_UI_STATE_FILE=str(root/'state.json'), DEAL_UI_STATE_LOCK_FILE=str(root/'state.lock'),
            WORKFLOW_DB_FILE=str(root/'runtime.sqlite3'))
        patched.start(); self.addCleanup(patched.stop)
        self.seq = 0
        sender = patch.object(bridge, 'send_message'); sender.start(); self.addCleanup(sender.stop)
        search = patch.object(bridge, 'search_creation_clients', return_value={'ok': True, 'clients': [{'id':'42','name':'Example','kind':'company'}]})
        search.start(); self.addCleanup(search.stop)

    def input(self, text):
        self.seq += 1; bridge.UI_CONTEXT = bridge.ui_state_store().bind('manager', str(self.seq))
        return bridge.handle_deal_ui('token', 'manager', text, _background=True)

    def test_wizard_preserves_title_and_client_and_writes_only_after_final_confirmation(self):
        with patch.object(bridge, 'run_create_megaplan_deal', return_value={'ok': True, 'id': '999', 'url': 'test'}) as create:
            self.input('➕ Создать сделку'); self.input('Lighting'); self.input('Example')
            self.assertEqual('deal_create_client_select',bridge.current_deal_ui_state('manager')['pending'])
            self.input('Клиент ID 42 — Example')
            state=bridge.current_deal_ui_state('manager'); spec=dict(state['deal_create_spec'])
            spec.update(items=[{'name':'Lamp','qty':2,'unit_price':100}],tax_mode='none')
            bridge.prepare_deal_creation_review('token','manager',spec)
            create.assert_not_called()
            self.input('✅ Создать подтверждённую сделку')
            create.assert_called_once()
            self.assertEqual('42',create.call_args.args[0]['client_id'])
            self.assertEqual('Lighting',create.call_args.args[0]['description'])
            self.assertEqual('999',bridge.current_deal_ui_state('manager')['current_deal_id'])

    def test_tax_answer_only_prepares_preview(self):
        self.seq+=1; bridge.UI_CONTEXT=bridge.ui_state_store().bind('manager',str(self.seq))
        bridge.update_deal_ui_state('manager',pending='deal_create_tax',deal_creation_active=True,
            deal_create_spec={'client_id':'42','client_name':'Example','description':'Lighting',
                              'items':[{'name':'Lamp','qty':1,'unit_price':100}]})
        with patch.object(bridge,'run_create_megaplan_deal') as create:
            self.input('Без НДС'); create.assert_not_called()
        self.assertEqual('deal_create_confirm',bridge.current_deal_ui_state('manager')['pending'])

    def test_stale_create_confirmation_never_falls_through_to_model(self):
        self.seq += 1
        bridge.UI_CONTEXT = bridge.ui_state_store().bind('manager', str(self.seq))
        bridge.update_deal_ui_state('manager', pending='deal_create_items',
            deal_create_spec={'user_request': '✅ Создать подтверждённую сделку'})
        with patch.object(bridge, 'run_create_megaplan_deal') as create, \
             patch.object(bridge, 'send_message') as send:
            self.assertTrue(self.input('✅ Создать подтверждённую сделку'))
        create.assert_not_called()
        self.assertIn('Сделка не создана', send.call_args.args[2])

    def test_description_only_legacy_create_is_disabled(self):
        with patch.object(bridge.subprocess,'run') as external:
            self.assertIsNone(bridge.create_megaplan_deal({},{}))
            external.assert_not_called()

    def test_economics_caption_reuses_existing_client_and_sends_requested_proposal(self):
        caption='На основании данного файла создай сделку с клиентом Меламори и пришли мне коммерческое предложение для Алексея'
        items=[{'name':'Монтажные работы','qty':1,'unit_price':310330,'cost_work':150000}]
        self.seq+=1; bridge.UI_CONTEXT=bridge.ui_state_store().bind('manager',str(self.seq))
        with patch.object(bridge,'parse_deal_economics_xlsx',return_value={'ok':True,'items':items}), \
             patch.object(bridge,'search_creation_clients',return_value={'ok':True,'clients':[{'id':'1002840','name':'Интерьер-дизайн Меламори','kind':'company'}]}) as lookup, \
             patch.object(bridge,'run_create_megaplan_deal',return_value={'ok':True,'id':'999','url':'test'}) as create, \
             patch.object(bridge,'send_deal_proposal') as proposal:
            self.assertTrue(bridge.prepare_economics_deal_request('token','manager',caption,'test.xlsx'))
            lookup.assert_called_once_with('Меламори')
            s=bridge.current_deal_ui_state('manager')
            self.assertEqual(s['pending'],'deal_create_tax')
            self.assertEqual(s['deal_create_spec']['client_id'],'1002840')
            self.assertFalse(s['deal_create_spec']['allow_new_client'])
            self.assertEqual(s['deal_creation_items'],items)
            create.assert_not_called()
            self.input('Без НДС'); create.assert_not_called()
            self.assertEqual(bridge.current_deal_ui_state('manager')['pending'],'deal_create_confirm')
            self.input('✅ Создать подтверждённую сделку')
            create.assert_called_once()
            proposal.assert_called_once_with('token','manager','999',recipient='Алексея')

    def test_failed_client_lookup_keeps_rows_and_never_offers_new_client(self):
        self.seq+=1; bridge.UI_CONTEXT=bridge.ui_state_store().bind('manager',str(self.seq))
        with patch.object(bridge,'parse_deal_economics_xlsx',return_value={'ok':True,'items':[{'name':'Item','qty':1,'unit_price':100}]}), \
             patch.object(bridge,'search_creation_clients',return_value={'ok':False}):
            bridge.prepare_economics_deal_request('token','manager','Создай сделку с клиентом Меламори','file.xlsx')
        s=bridge.current_deal_ui_state('manager')
        self.assertEqual(s['pending'],'deal_create_client')
        self.assertFalse(s['deal_create_spec']['allow_new_client'])
        self.assertEqual(len(s['deal_creation_items']),1)


if __name__=='__main__': unittest.main()
