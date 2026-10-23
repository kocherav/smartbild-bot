import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bridge
from human_qa_harness import FakeMegaplan, FakeTelegram


class MorningBriefHumanQATests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.crm = FakeMegaplan(Path(self.temp.name))
        self.telegram = FakeTelegram('owner')
        self.crm.add_client('1', 'Должник')
        self.crm.add_client('2', 'Оплаченный')
        self.crm.add_client('3', 'Завершённый')
        old = '2026-09-20T06:00:00+00:00'
        self.crm.add_deal('101', '1', 'Застрявшая', positions=(('Работа', 1, 10000),), created_at=old)['updated_at'] = old
        self.crm.add_deal('102', '2', 'Оплаченная', positions=(('Работа', 1, 20000),), created_at=old)['updated_at'] = '2026-10-22T06:00:00+00:00'
        self.crm.add_deal('103', '3', 'Готовая', status_id='3', positions=(('Работа', 1, 30000),), created_at=old)['updated_at'] = old
        self.crm.statuses['3'] = 'Завершена'
        first = self.crm.add_invoice('101', [{'name': 'Работа', 'qty': 1, 'price': 10000}])
        first['created_at'] = old
        paid = self.crm.add_invoice('102', [{'name': 'Работа', 'qty': 1, 'price': 20000}])
        paid['created_at'] = old
        self.crm.bank_transactions.append({'deal_id': '102', 'amount': '20000', 'status': 'assigned',
                                           'direction': 'income'})

    def _send(self, result):
        with (patch.object(bridge, 'RUNTIME_ACTIVE', True),
              patch.object(bridge, 'UI_CONTEXT', None),
              patch.object(bridge, 'WORKFLOW_DB_FILE', str(Path(self.temp.name) / 'workflow.sqlite3')),
              patch.object(bridge, 'DEAL_UI_STATE_FILE', str(Path(self.temp.name) / 'state.json')),
              patch.object(bridge, 'DEAL_UI_STATE_LOCK_FILE', str(Path(self.temp.name) / 'state.lock')),
              patch.object(bridge, 'tg_api', side_effect=self.telegram.api),
              patch.object(bridge, 'run_morning_brief', return_value=result)):
            bridge.send_morning_brief('qa', 'owner', {'invoice_overdue_days': 7, 'deal_stale_days': 14,
                                                       'completed_statuses': ['заверш']})

    def test_debtor_and_stale_deal_visible_paid_and_completed_absent_and_button_opens(self):
        result = self.crm.cli_morning_brief('build', {'invoice_days': 7, 'stale_days': 14,
                                                       'completed_statuses': ['заверш']})
        self._send(result)
        text = '\n'.join(event['text'] for event in self.telegram.events)
        self.assertIn('Должник', text)
        self.assertNotIn('Оплаченный', text)
        self.assertNotIn('Завершённый', text)
        self.assertIn('№101 · открыть сделку', self.telegram.visible_inline())
        callback, _ = self.telegram.visible_inline()['№101 · открыть сделку']
        from workflow_runtime import Store
        control = Store(str(Path(self.temp.name) / 'workflow.sqlite3')).take_control('owner', callback[3:])
        self.assertTrue(control['ok'])
        self.assertIn('№101', control['text'])
        with (patch.object(bridge, 'run_background_job', side_effect=lambda job, *args, **kwargs: job()),
              patch.object(bridge, 'run_deal_browser', return_value={
                  'ok': True, 'deal': self.crm.summary(self.crm.deals['101'])}),
              patch.object(bridge, 'send_message') as send):
            self.assertTrue(bridge.handle_deal_ui('qa', 'owner', control['text']))
        self.assertIn('Сделка №101', send.call_args.args[2])

    def test_crm_failure_is_not_reported_as_empty_success(self):
        self._send({'ok': False, 'error': 'таймаут'})
        text = '\n'.join(event['text'] for event in self.telegram.events)
        self.assertIn('НЕ СОБРАН', text)
        self.assertIn('таймаут', text)
        self.assertNotIn('задач нет', text)


    def test_long_list_shows_the_largest_first_and_counts_the_rest(self):
        stale = [{'deal_id': str(200 + n), 'client': f'Клиент {n}', 'amount': str(1000 * n), 'days': 30,
                  'status': 'Закупка'} for n in range(1, 16)]
        self._send({'ok': True, 'overdue': [], 'stale': stale})
        text = self.telegram.events[-1]['text']
        self.assertIn('…и ещё 5 сделок без движения.', text)
        self.assertLess(text.index('№215'), text.index('№206'), 'Крупнейшие сделки идут первыми')
        self.assertNotIn('№205', text)
        self.assertEqual(10, len([label for label in self.telegram.visible_inline() if 'открыть сделку' in label]))


if __name__ == '__main__':
    unittest.main()
