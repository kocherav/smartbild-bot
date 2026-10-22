import json
import unittest
from unittest.mock import patch
import bridge

class DashboardNavigationTests(unittest.TestCase):
    def test_compact_menu_and_single_dashboard_entry(self):
        self.assertEqual([[b['text'] for b in row] for row in bridge.MAIN_KEYBOARD['keyboard']],
                         [['🤝 Сделки','🏦 Деньги'],['🧰 Монтаж','☰ Ещё']])
        self.assertTrue(bridge.persistent_navigation(bridge.MAIN_KEYBOARD))
        self.assertFalse(bridge.persistent_navigation(bridge.DEALS_KEYBOARD))
        self.assertFalse(any(b.get('text')=='📊 Пульт сделок' for row in bridge.MAIN_KEYBOARD['keyboard'] for b in row))
    def test_repeatable_launch_is_not_a_workflow_callback(self):
        with patch.object(bridge,'MANAGER_CHAT_ID','owner'),patch.object(bridge,'send_message') as send,patch.object(bridge,'update_deal_ui_state') as update:
            for _ in range(2):self.assertTrue(bridge.handle_global_navigation('token','owner','📊 Пульт сделок'))
            self.assertEqual(send.call_count,2);update.assert_not_called()
            for call in send.call_args_list:
                btn=call.args[3]['inline_keyboard'][0][0]
                self.assertEqual(btn['web_app']['url'],bridge.DASHBOARD_URL)
                self.assertNotIn('callback_data',btn)
    def test_command_owner_only(self):
        with patch.object(bridge,'MANAGER_CHAT_ID','owner'),patch.object(bridge,'send_message') as send:
            self.assertFalse(bridge.handle_global_navigation('token','other','/dashboard'));send.assert_not_called()
            self.assertTrue(bridge.handle_global_navigation('token','owner','/dashboard'))
    def test_deals_do_not_duplicate_dashboard_launch(self):
        with patch.object(bridge,'send_message') as send,patch.object(bridge,'update_deal_ui_state'):
            self.assertTrue(bridge.handle_global_navigation('token','owner','/deals'))
            self.assertEqual(send.call_count,1)
            self.assertEqual(send.call_args.args[3],bridge.DEALS_KEYBOARD)
    def test_startup_restores_menu_for_owner_only(self):
        with patch.object(bridge,'MANAGER_CHAT_ID','owner'),patch.object(bridge,'tg_api',return_value={'ok':True}) as api:
            bridge.configure_bot_commands('token')
            call=[c for c in api.call_args_list if c.args[1]=='setChatMenuButton'][0]
            self.assertEqual(call.args[2]['chat_id'],'owner')
            self.assertEqual(json.loads(call.args[2]['menu_button'])['web_app']['url'],bridge.DASHBOARD_URL)

if __name__=='__main__':unittest.main()
