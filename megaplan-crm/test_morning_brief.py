import datetime as dt
import unittest
from unittest.mock import patch

import morning_brief


class FakeAPI:
    def __init__(self, invoices):
        self.invoices = invoices
        self.calls = []

    def _call(self, method, path, params=None):
        self.calls.append((method, path, params))
        if path == '/invoice':
            return {'data': self.invoices, 'meta': {'pagination': {'hasMoreNext': False}}}
        raise AssertionError(path)


class MorningBriefTests(unittest.TestCase):
    def test_batch_invoices_local_payments_and_completed_filter(self):
        now = dt.datetime(2026, 10, 23, 6, tzinfo=dt.timezone.utc)
        old = '2026-09-20T06:00:00+00:00'
        deals = [
            {'id': '1', 'contractor': {'name': 'Должник'}, 'state': {'name': 'В работе'},
             'timeCreated': {'value': old}, 'timeUpdated': {'value': old}, 'price': {'value': '100'}},
            {'id': '2', 'contractor': {'name': 'Оплаченный'}, 'state': {'name': 'В работе'},
             'timeCreated': {'value': old}, 'timeUpdated': {'value': now.isoformat()}, 'price': {'value': '200'}},
            {'id': '3', 'contractor': {'name': 'Готовый'}, 'state': {'name': 'Завершена'},
             'timeCreated': {'value': old}, 'timeUpdated': {'value': old}, 'price': {'value': '300'}},
        ]
        invoices = [
            {'id': '11', 'deal': {'id': '1'}, 'number': 'A', 'status': 'drawn',
             'timeCreated': {'value': old}, 'sum': {'value': '100'}},
            {'id': '12', 'deal': {'id': '2'}, 'number': 'B', 'status': 'drawn',
             'timeCreated': {'value': old}, 'sum': {'value': '200'}},
        ]
        bank = {'transactions': [{'deal_id': '2', 'amount': '200', 'status': 'assigned', 'direction': 'income'}]}
        api = FakeAPI(invoices)
        with (patch.object(morning_brief.deal_browser, 'fetch_all', return_value=deals),
              patch.object(morning_brief.bank_statement, 'load_registry', return_value=bank)):
            result = morning_brief.build(api, now=now, invoice_days=7, stale_days=14,
                                         completed_statuses=['заверш'])
        self.assertEqual(['1'], [x['deal_id'] for x in result['overdue']])
        self.assertEqual(['1'], [x['deal_id'] for x in result['stale']])
        self.assertEqual(1, len(api.calls), 'счета должны читаться пакетом, не по сделке')

    def test_partial_payment_leaves_exact_remainder(self):
        old = '2026-09-20T06:00:00+00:00'
        deal = {'id': '1', 'contractor': {'name': 'Клиент'}, 'state': {'name': 'В работе'},
                'timeCreated': {'value': old}, 'timeUpdated': {'value': old}, 'price': {'value': '100'}}
        invoice = {'id': '11', 'deal': {'id': '1'}, 'status': 'drawn',
                   'timeCreated': {'value': old}, 'sum': {'value': '100'}}
        with (patch.object(morning_brief.deal_browser, 'fetch_all', return_value=[deal]),
              patch.object(morning_brief.bank_statement, 'load_registry', return_value={'transactions': [
                  {'deal_id': '1', 'amount': '40', 'status': 'assigned', 'direction': 'income'}]})):
            result = morning_brief.build(FakeAPI([invoice]), now=dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc),
                                         completed_statuses=['заверш'])
        self.assertEqual('60', result['overdue'][0]['remainder'])


if __name__ == '__main__':
    unittest.main()
