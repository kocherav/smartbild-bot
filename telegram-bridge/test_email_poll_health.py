"""09.11: bank notifications were not processed for days and nobody was told."""
import os
import tempfile
import unittest
from unittest import mock

import bridge


class EmailPollHealthTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        patches = [mock.patch.object(bridge, 'EMAIL_POLL_HEALTH_FILE', os.path.join(self.dir, 'h.json')),
                   mock.patch.object(bridge, 'BASE_DIR', self.dir),
                   mock.patch.object(bridge.periodic_schedule, 'claim', return_value=True)]
        for p in patches:
            p.start(); self.addCleanup(p.stop)

    def poll(self, *results):
        with mock.patch.object(bridge, 'run_email_payment_monitor', side_effect=list(results)) as run, \
             mock.patch.object(bridge, 'send_message') as send:
            bridge.poll_email_payments('t', 'owner')
        return run, [c.args[2] for c in send.call_args_list]

    def test_one_failure_is_quiet_two_in_a_row_tell_the_owner_once_a_day(self):
        _, first = self.poll({'ok': False, 'error': 'LOGIN failed'})
        self.assertEqual([], first)
        _, second = self.poll({'ok': False, 'error': 'LOGIN failed'})
        self.assertEqual(1, len(second)); self.assertIn('не работает (2 раза подряд): LOGIN failed', second[0])
        _, third = self.poll({'ok': False, 'error': 'LOGIN failed'})
        self.assertEqual([], third, 'не чаще раза в сутки')
        _, healed = self.poll({'ok': True, 'created': [], 'failed': []})
        self.assertEqual(['✅ Проверка банковских уведомлений снова работает.'], healed)

    def test_unreadable_letters_are_reported(self):
        _, sent = self.poll({'ok': True, 'created': [], 'failed': [
            {'subject': 'Уведомление о платеже', 'error': 'письмо не соответствует уведомлению о платеже Альфа-Банка'}]})
        self.assertEqual(1, len(sent)); self.assertIn('НЕ учтены', sent[0])

    def test_backlog_is_read_in_several_steps_at_once(self):
        run, sent = self.poll({'ok': True, 'created': [{'payment_number': '1', 'date': '01.11.2026', 'amount': 10}],
                               'failed': [], 'more': True},
                              {'ok': True, 'created': [{'payment_number': '2', 'date': '02.11.2026', 'amount': 20}],
                               'failed': [], 'more': False})
        self.assertEqual(2, run.call_count)
        self.assertEqual(2, len([s for s in sent if 'Получено банковское уведомление' in s]))


if __name__ == '__main__':
    unittest.main()
