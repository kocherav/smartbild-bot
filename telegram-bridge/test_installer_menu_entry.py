"""Owner 23.11: the installer report waiting for approval must be reachable from «🧰 Монтаж»."""
import unittest
from unittest.mock import patch

import bridge


class InstallerReportInMenu(unittest.TestCase):
    def run_ui(self, text, state):
        sent = []
        with patch.object(bridge, 'MANAGER_CHAT_ID', '1'), \
             patch.object(bridge, 'current_deal_ui_state', return_value=state), \
             patch.object(bridge, 'update_deal_ui_state'), \
             patch.object(bridge, 'send_message', side_effect=lambda t, c, msg, kb=None, *a, **k: sent.append((msg, kb))):
            bridge.handle_global_navigation('token', '1', text) or bridge.handle_deal_ui('token', '1', text)
        return sent

    def buttons(self, keyboard):
        return [b['text'] for row in keyboard['keyboard'] for b in row]

    def test_pending_report_adds_open_button_to_installation_menu(self):
        sent = self.run_ui('🧰 Монтаж', {'incoming_installer_report': {'report_date': '20.11.2026', 'exceptions': []}})
        self.assertIn('отчёт монтажника от 20.11.2026', sent[0][0])
        self.assertEqual(bridge.INSTALLER_OPEN_REPORT, self.buttons(sent[0][1])[0])

    def test_no_pending_report_keeps_the_usual_menu(self):
        sent = self.run_ui('🧰 Монтаж', {})
        self.assertNotIn(bridge.INSTALLER_OPEN_REPORT, self.buttons(sent[0][1]))

    def test_open_button_without_a_report_answers_plainly(self):
        sent = self.run_ui(bridge.INSTALLER_OPEN_REPORT, {})
        self.assertEqual('Отчётов монтажника на утверждении нет.', sent[0][0])

    def test_open_button_with_a_report_opens_it(self):
        sent = self.run_ui(bridge.INSTALLER_OPEN_REPORT, {'incoming_installer_report': {'report_date': '20.11.2026', 'exceptions': []}})
        self.assertIs(bridge.INSTALLER_REPORT_REVIEW_KEYBOARD, sent[0][1])


if __name__ == '__main__':
    unittest.main()
