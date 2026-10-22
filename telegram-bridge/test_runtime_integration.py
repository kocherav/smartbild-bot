from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import bridge
import runtime_guards
from ui_context import StateStore
from workflow_runtime import Store


class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patch = patch.multiple(bridge, RUNTIME_ACTIVE=True,
            WORKFLOW_DB_FILE=str(self.root / 'operations.sqlite3'),
            DEAL_UI_STATE_FILE=str(self.root / 'state.json'),
            DEAL_UI_STATE_LOCK_FILE=str(self.root / 'state.lock'), UI_CONTEXT=None)
        self.patch.start(); self.addCleanup(self.patch.stop)
        bridge.UI_CONTEXT = bridge.ui_state_store().bind('owner', '1')
        bridge.UI_CONTEXT.confirmed_control=True
        bridge.update_deal_ui_state('owner',pending='deal_create_confirm')

    def test_receipt_and_selection_are_independent(self):
        action = Mock(return_value={'ok': True, 'id': 'created'})
        guarded = runtime_guards.decorate(vars(bridge), 'run_create_megaplan_deal', action, None)
        spec = {'client_id': 'customer', 'items': [{'name': 'Item'}]}
        first, second = guarded(spec), guarded(spec)
        self.assertEqual('created', second['id'])
        action.assert_called_once()
        self.assertTrue(second['_reused'])

    def test_model_service_block_without_actual_callback_cannot_write(self):
        bridge.UI_CONTEXT.confirmed_control=False
        action=Mock()
        guarded=runtime_guards.decorate(vars(bridge),'run_sync_deal_kp',action,None)
        self.assertTrue(guarded({'deal_id':'1','kp':{}})['no_effect'])
        action.assert_not_called()

    def test_executor_and_installation_sync_require_current_confirmation(self):
        bridge.UI_CONTEXT.confirmed_control=False
        for name, action_name in (('run_deal_browser','set_executor'),('run_installation_workflow','sync_executor')):
            with self.subTest(name=name):
                action=Mock()
                guarded=runtime_guards.decorate(vars(bridge),name,action,runtime_guards.WRITE_ACTIONS[name])
                result=guarded({'action':action_name,'deal_id':'900'})
                self.assertTrue(result['no_effect'])
                action.assert_not_called()

    def test_readonly_preview_does_not_require_write_confirmation(self):
        bridge.UI_CONTEXT.confirmed_control=False
        action=Mock(return_value={'ok':True,'rows':[]})
        guarded=runtime_guards.decorate(vars(bridge),'run_sync_deal_kp',action,None)
        self.assertTrue(guarded({'deal_id':'1','preview':True})['ok'])
        action.assert_called_once()

    def test_stale_mutation_is_stopped_before_handler(self):
        action = Mock()
        guarded = runtime_guards.decorate(vars(bridge), 'run_create_megaplan_deal', action, None)
        bridge.ui_state_store().bind('owner', '2')
        self.assertTrue(guarded({'items': []})['stale'])
        action.assert_not_called()

    def test_stale_worker_cannot_restore_previous_selected_deal(self):
        bridge.update_deal_ui_state('owner', current_deal_id='first')
        newer = bridge.ui_state_store().bind('owner', '2')
        bridge.ui_state_store().update('owner', {'current_deal_id': 'second'}, newer)
        bridge.update_deal_ui_state('owner', current_deal_id='first')
        self.assertEqual('second', bridge.load_deal_ui_state()['owner']['current_deal_id'])

    def test_keyboard_is_bound_callback_not_plain_confirmation(self):
        with patch.object(bridge, 'tg_api', return_value={'ok': True}) as api:
            bridge.send_message('not-a-token', 'owner', 'Preview', {'keyboard': [[{'text': '✅ Применить'}]]})
        import json
        markup = json.loads(api.call_args.args[2]['reply_markup'])
        self.assertIn('inline_keyboard', markup)
        token = markup['inline_keyboard'][0][0]['callback_data'][3:]
        self.assertTrue(Store(bridge.WORKFLOW_DB_FILE).take_control('owner', token)['ok'])

    def test_stale_result_cannot_publish_new_controls(self):
        bridge.ui_state_store().bind('owner', '2')
        with patch.object(bridge, 'tg_api', return_value={'ok': True}) as api:
            bridge.send_message('not-a-token', 'owner', 'Old result', {'keyboard': [[{'text': '✅ Применить'}]]})
        self.assertNotIn('reply_markup', api.call_args.args[2])

    def test_bottom_navigation_does_not_expire_report_confirmation(self):
        import json
        store=Store(bridge.WORKFLOW_DB_FILE)
        control=store.keyboard('owner',[[{'text':'✅ Объекты верны'}]])['inline_keyboard'][0][0]['callback_data'][3:]
        with patch.object(bridge,'tg_api',return_value={'ok':True}) as api:
            for menu in (bridge.MAIN_KEYBOARD,bridge.INSTALLER_USER_KEYBOARD,bridge.INSTALLER_MENU_KEYBOARD):
                bridge.send_message('fake','owner','Menu',menu)
                markup=json.loads(api.call_args.args[2]['reply_markup'])
                self.assertIn('keyboard',markup);self.assertNotIn('inline_keyboard',markup)
                self.assertTrue(markup['is_persistent']);self.assertFalse(markup['one_time_keyboard'])
        self.assertTrue(store.take_control('owner',control)['ok'])

    def test_dynamic_choices_and_payment_confirmation_stay_inline(self):
        import json
        with patch.object(bridge,'tg_api',return_value={'ok':True}) as api:
            for menu in (bridge.INSTALLER_PAYMENT_KEYBOARD,bridge.TAX_KEYBOARD,{'keyboard':[[{'text':'№861 — объект'}]]}):
                bridge.send_message('fake','owner','Choice',menu)
                markup=json.loads(api.call_args.args[2]['reply_markup'])
                self.assertIn('inline_keyboard',markup);self.assertNotIn('keyboard',markup)

    def test_background_bottom_menu_keeps_active_screen_and_state(self):
        import json
        before=bridge.current_deal_ui_state('owner')
        store=Store(bridge.WORKFLOW_DB_FILE)
        control=store.keyboard('owner',[[{'text':'✅ Принять отчёт'}]])['inline_keyboard'][0][0]['callback_data'][3:]
        with patch.object(bridge,'UI_CONTEXT',None),patch.object(bridge,'tg_api',return_value={'ok':True}) as api:
            bridge.send_message('fake','owner','Menu',bridge.MAIN_KEYBOARD)
            self.assertIn('keyboard',json.loads(api.call_args.args[2]['reply_markup']))
        self.assertEqual(before,bridge.current_deal_ui_state('owner'))
        self.assertTrue(store.take_control('owner',control)['ok'])

    def test_cancel_is_navigation_before_pending_contact_name(self):
        bridge.update_deal_ui_state('owner',pending='installation_contact_create_name')
        with patch.object(bridge,'send_message'),patch.object(bridge,'run_installation_workflow') as api:
            self.assertTrue(bridge.handle_global_navigation('token','owner','❌ Отмена'))
        self.assertIsNone(bridge.current_deal_ui_state('owner').get('pending')); api.assert_not_called()

if __name__ == '__main__':
    unittest.main()
