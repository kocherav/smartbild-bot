"""Owner 24.11: «📎 Цены из КП и счетов» — supplier documents price the open deal after his button."""
import types
import unittest
from unittest.mock import patch

import deal_price_flow as flow


class FakeIO:
    def __init__(self, state):
        self.st, self.sent, self.tables, self.applied = dict(state), [], [], []
        self.deal_keyboard = {'keyboard': []}

    def send(self, chat_id, text, keyboard=None):
        self.sent.append((text, keyboard))

    def update(self, chat_id, **kw):
        self.st.update(kw)

    def state(self, chat_id):
        return dict(self.st)

    def send_table(self, *a):
        self.tables.append(a)

    def apply_rows(self, payload):
        self.applied.append(payload)
        return {'ok': True, 'applied': payload['rows'], 'kept': []}


KP = {'ok': True, 'kind': 'kp', 'supplier': 'ООО Арктика', 'file': 'kp.pdf',
      'rows': [{'name': 'Диффузор щелевой Invisiline SMART-40-B-2000-2', 'qty': 2, 'unit': 'шт', 'price': 40000, 'amount': 80000}]}
UNCLEAR = {**KP, 'kind': None, 'file': 'doc.pdf'}


class Flow(unittest.TestCase):
    def go(self, io, text, ledger=None, sources=None):
        jobs = []
        with patch.object(flow, 'run_sources', side_effect=sources or (lambda c, p, py: KP)):
            handled = flow.handle_text(io, 1, io.state(1), text, lambda d: ledger, 'py', jobs.append)
            for job in jobs:
                job()
        return handled

    def test_full_route_with_kp_discount_and_apply(self):
        io = FakeIO({'current_deal_id': '907'})
        self.assertTrue(self.go(io, flow.BUTTON))
        self.assertEqual('deal_price_docs', io.st['pending'])
        with patch.object(flow, 'run_sources', return_value=KP):
            flow.add_file(io, 1, io.state(1), '/tmp/kp.pdf', 'py')
        self.assertEqual('deal_price_discount', io.st['pending'])
        self.assertIn('Скидка 40%', [b['text'] for row in io.sent[-1][1]['keyboard'] for b in row])
        self.assertTrue(self.go(io, 'Скидка 15%'))
        self.assertEqual(15.0, io.st['price_docs'][0]['discount'])
        proposal = {'offer_row_id': '1', 'offer_id': '2', 'name': 'Диффузор', 'sell_price': 40000, 'cost_material': 34000,
                    'mark': 'КП ООО Арктика, скидка 15%'}
        seen = {}

        def sources(command, payload, python):
            seen[command] = payload
            return {'ok': True, 'proposals': [proposal], 'skipped': []}
        self.go(io, flow.DONE, ledger=[{'offer_row_id': '1', 'name': 'Диффузор', 'sell_price': 0}], sources=sources)
        self.assertEqual(15.0, seen['propose']['documents'][0]['discount'])
        self.assertEqual('deal_price_review', io.st['pending'])
        self.assertIn('В сделку ничего не записано', io.sent[-1][0]); self.assertEqual(1, len(io.tables))
        self.go(io, flow.APPLY)
        self.assertEqual([proposal], io.applied[0]['rows'])
        self.assertIsNone(io.st['pending'])

    def test_unclear_document_asks_invoice_or_kp(self):
        io = FakeIO({'current_deal_id': '907', 'pending': 'deal_price_docs', 'price_docs': []})
        with patch.object(flow, 'run_sources', return_value=UNCLEAR):
            flow.add_file(io, 1, io.state(1), '/tmp/doc.pdf', 'py')
        self.assertEqual('deal_price_kind', io.st['pending'])
        self.go(io, flow.IS_INVOICE)
        self.assertEqual(('invoice', 'deal_price_docs'), (io.st['price_docs'][0]['kind'], io.st['pending']))

    def test_own_discount_figure_and_bounds(self):
        io = FakeIO({'pending': 'deal_price_discount', 'price_docs': [dict(KP, discount=None)]})
        self.go(io, '17,5')
        self.assertEqual(17.5, io.st['price_docs'][0]['discount'])
        io = FakeIO({'pending': 'deal_price_discount', 'price_docs': [dict(KP, discount=None)]})
        self.go(io, '95')
        self.assertIsNone(io.st['price_docs'][0]['discount'])

    def test_without_an_open_deal_nothing_starts(self):
        io = FakeIO({})
        self.go(io, flow.BUTTON)
        self.assertNotIn('pending', io.st)
        self.assertIn('откройте сделку', io.sent[-1][0])

    def test_cancel_writes_nothing(self):
        io = FakeIO({'pending': 'deal_price_review', 'price_proposals': [{'name': 'x'}]})
        self.go(io, flow.CANCEL)
        self.assertEqual([], io.applied); self.assertIsNone(io.st['pending'])


if __name__ == '__main__':
    unittest.main()
