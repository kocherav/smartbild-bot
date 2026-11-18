import datetime as dt
import unittest
from unittest.mock import patch

import morning_brief


# Fields Megaplan accepts for /invoice (the dashboard snapshot uses them daily). Anything
# else fails the whole request: «Invoice have not this fields: timeCreated» (422, 11.2026).
INVOICE_FIELDS = {'deal', 'sum', 'status', 'number', 'invoiceDate', 'financeOperations',
                  'financeOperationsCount', 'recipient'}


def day(iso):
    moment = dt.datetime.fromisoformat(iso)
    return {'contentType': 'DateOnly', 'year': moment.year, 'month': moment.month - 1, 'day': moment.day}


class FakeAPI:
    def __init__(self, invoices):
        self.invoices = invoices
        self.calls = []

    def _call(self, method, path, params=None):
        self.calls.append((method, path, params))
        if path == '/invoice':
            unknown = set((params or {}).get('fields') or []) - INVOICE_FIELDS
            if unknown:
                raise RuntimeError(f'Megaplan API error 422: Invoice have not this fields: {sorted(unknown)}')
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
             'invoiceDate': day(old), 'sum': {'value': '100'}},
            {'id': '12', 'deal': {'id': '2'}, 'number': 'B', 'status': 'drawn',
             'invoiceDate': day(old), 'sum': {'value': '200'}},
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
                   'invoiceDate': day(old), 'sum': {'value': '100'}}
        with (patch.object(morning_brief.deal_browser, 'fetch_all', return_value=[deal]),
              patch.object(morning_brief.bank_statement, 'load_registry', return_value={'transactions': [
                  {'deal_id': '1', 'amount': '40', 'status': 'assigned', 'direction': 'income'}]})):
            result = morning_brief.build(FakeAPI([invoice]), now=dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc),
                                         completed_statuses=['заверш'])
        self.assertEqual('60', result['overdue'][0]['remainder'])

    def test_money_for_a_paid_invoice_does_not_hide_a_later_debt(self):
        # QA 23.10: payments were allocated only to unpaid invoices, so the money
        # that settled invoice A "paid" invoice B and the debtor vanished.
        old, older = '2026-09-20T06:00:00+00:00', '2026-09-01T06:00:00+00:00'
        deal = {'id': '1', 'contractor': {'name': 'Клиент'}, 'state': {'name': 'В работе'},
                'timeCreated': {'value': older}, 'timeUpdated': {'value': old}, 'price': {'value': '150'}}
        invoices = [{'id': '10', 'deal': {'id': '1'}, 'number': 'A', 'status': 'paid',
                     'invoiceDate': day(older), 'sum': {'value': '100'}},
                    {'id': '11', 'deal': {'id': '1'}, 'number': 'B', 'status': 'drawn',
                     'invoiceDate': day(old), 'sum': {'value': '50'}}]
        bank = {'transactions': [{'deal_id': '1', 'amount': '100', 'status': 'assigned', 'direction': 'income'}]}
        with (patch.object(morning_brief.deal_browser, 'fetch_all', return_value=[deal]),
              patch.object(morning_brief.bank_statement, 'load_registry', return_value=bank)):
            result = morning_brief.build(FakeAPI(invoices), now=dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc),
                                         completed_statuses=['заверш'])
        self.assertEqual([('B', '50')], [(x['invoice_number'], x['remainder']) for x in result['overdue']])

    def test_only_fields_megaplan_has_are_requested(self):
        # Every morning since 11.2026: «Утренний список дел НЕ СОБРАН … 422 … timeCreated».
        api = FakeAPI([])
        with (patch.object(morning_brief.deal_browser, 'fetch_all', return_value=[]),
              patch.object(morning_brief.bank_statement, 'load_registry', return_value={'transactions': []})):
            self.assertTrue(morning_brief.build(api)['ok'])
        self.assertLessEqual(set(api.calls[0][2]['fields']), INVOICE_FIELDS)

    def test_invoice_age_counts_from_the_invoice_date(self):
        deal = {'id': '1', 'contractor': {'name': 'Клиент'}, 'state': {'name': 'В работе'},
                'timeUpdated': {'value': '2026-10-22T06:00:00+00:00'}, 'price': {'value': '100'}}
        recent = {'id': '11', 'deal': {'id': '1'}, 'status': 'drawn', 'invoiceDate': day('2026-10-20T00:00:00'),
                  'sum': {'value': '100'}}
        with (patch.object(morning_brief.deal_browser, 'fetch_all', return_value=[deal]),
              patch.object(morning_brief.bank_statement, 'load_registry', return_value={'transactions': []})):
            fresh = morning_brief.build(FakeAPI([recent]), now=dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc))
            late = morning_brief.build(FakeAPI([recent]), now=dt.datetime(2026, 11, 3, tzinfo=dt.timezone.utc))
        self.assertEqual([], fresh['overdue'], 'счёт от 20.10 на 23.10 ещё не просрочен')
        self.assertEqual(14, late['overdue'][0]['days'])

    def test_megaplan_result_decides_open_deals_when_status_names_are_missing(self):
        # 18.11: 829 of 859 «stale» deals had a compact state without a name and counted as
        # open; 281 of 312 «overdue» invoices were older than a year.
        old = '2025-06-01T06:00:00+00:00'
        def deal(ident, result):
            return {'id': ident, 'contractor': {'name': f'Клиент {ident}'}, 'state': {'id': '9'},
                    'result': result, 'timeUpdated': {'value': old}, 'price': {'value': '100'}}
        deals = [deal('1', 'active'), deal('2', 'won'), deal('3', 'lost')]
        invoices = [{'id': f'1{n}', 'deal': {'id': n}, 'number': n, 'status': 'drawn',
                     'invoiceDate': day(old), 'sum': {'value': '100'}} for n in ('1', '2', '3')]
        with (patch.object(morning_brief.deal_browser, 'fetch_all', return_value=deals),
              patch.object(morning_brief.bank_statement, 'load_registry', return_value={'transactions': []})):
            result = morning_brief.build(FakeAPI(invoices), now=dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc),
                                         completed_statuses=['заверш'])
        self.assertEqual(['1'], [x['deal_id'] for x in result['stale']], 'закрытые сделки — не «без движения»')
        self.assertEqual(['1'], [x['deal_id'] for x in result['overdue']], 'счета закрытых сделок — история')

    def test_status_names_still_decide_for_a_cache_without_result(self):
        old = '2026-09-01T06:00:00+00:00'
        deals = [{'id': '1', 'contractor': {'name': 'А'}, 'state': {'id': '1', 'name': 'Заказ'},
                  'timeUpdated': {'value': old}, 'price': {'value': '1'}},
                 {'id': '2', 'contractor': {'name': 'Б'}, 'state': {'id': '2', 'name': 'Завершена'},
                  'timeUpdated': {'value': old}, 'price': {'value': '1'}}]
        with (patch.object(morning_brief.deal_browser, 'fetch_all', return_value=deals),
              patch.object(morning_brief.bank_statement, 'load_registry', return_value={'transactions': []})):
            result = morning_brief.build(FakeAPI([]), now=dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc),
                                         completed_statuses=['заверш'])
        self.assertEqual(['1'], [x['deal_id'] for x in result['stale']])


if __name__ == '__main__':
    unittest.main()
