import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import deal_proposal as kp


def example():
    return {'id': '42', 'contractor': {'name': 'Тестовый клиент'}, 'description': 'Освещение',
            'price': {'currency': 'RUB', 'value': '252108.80'},
            'state': {'id': '131'}, 'stateTimeUpdated': {'value': '2026-09-29T10:00:00Z'},
            'positions': [{'quantity': 200, 'price': {'currency': 'RUB', 'value': 1575.68},
                           'discount': {'value': 20}, 'sum': {'currency': 'RUB', 'value': '252108.80'},
                           'tax': {'rate': -1}, 'offer': {'name': 'Лента', 'unit': {'name': 'м'},
                                                       'cost_material': 'SECRET_PURCHASE_PRICE'}}]}


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.patch = patch.object(kp, 'ROOT', self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        # The company letterhead lives only on the server; the layout and totals
        # are checked on a blank A4 of the same size.
        from pypdf import PdfWriter
        letterhead = self.root / 'letterhead.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=595.28, height=841.89)
        with open(letterhead, 'wb') as target:
            writer.write(target)
        letterhead_patch = patch.object(kp, 'LETTERHEAD', letterhead)
        letterhead_patch.start()
        self.addCleanup(letterhead_patch.stop)

    def test_discount_and_fractional_price(self):
        data = kp.snapshot(example())
        self.assertEqual(data['total'], '252108.80')
        self.assertEqual(kp.dec(data['rows'][0]['total']) / 200, kp.dec('1260.544'))
        self.assertNotIn('SECRET', str(data))
        self.assertNotIn('discount', str(data))

    def test_fractional_quantity_preserved(self):
        d = example()
        d['positions'][0]['quantity'] = 2.75
        self.assertEqual(kp.snapshot(d)['rows'][0]['qty'], '2.75')

    def test_mismatch_rejected(self):
        d = example(); d['price']['value'] = 123
        with self.assertRaisesRegex(ValueError, 'не совпадают'):
            kp.snapshot(d)

    def test_missing_or_foreign_amount_rejected(self):
        for v in (None, {'value': 10, 'currency': 'EUR'}):
            d = example(); d['positions'][0]['sum'] = v
            with self.assertRaises(ValueError):
                kp.snapshot(d)

    def test_invalid_quantity_rejected(self):
        for qty in (0, -1, 'NaN', 'Infinity'):
            d = example(); d['positions'][0]['quantity'] = qty
            with self.assertRaises(ValueError):
                kp.snapshot(d)

    def test_render_long_pdf_has_last_rows_and_total_without_private_data(self):
        from pypdf import PdfReader
        data = kp.snapshot(example())
        data['date'] = '29.09.2026'
        data['recipient'] = 'Уважаемая Татьяна,'
        data['rows'] = [{'name': f'PUBLIC-ROW-{i:03d} длинная позиция спецификации',
                         'qty': '2.75', 'unit': 'м', 'total': '27.50', 'tax_rate': '-1'}
                        for i in range(1, 81)]
        data['total'] = '2200.00'
        path = self.root / 'long.pdf'
        kp.render(data, path)
        pdf = PdfReader(str(path))
        self.assertGreaterEqual(len(pdf.pages), 3)
        text = '\n'.join(p.extract_text() for p in pdf.pages)
        for i in range(1, 81):
            self.assertEqual(text.count(f'PUBLIC-ROW-{i:03d}'), 2 if i <= 6 else 1)
        self.assertIn('2 200,00', text)
        self.assertNotIn('SECRET_PURCHASE_PRICE', text)

    def api(self):
        api = Mock()
        def call(method, path, **kwargs):
            if path == '/deal/42': return {'data': example()}
            if path in ('/unit', '/tax'): return {'data': []}
            if path == '/deal/42/allFiles': return {'data': [{'id': '7'}]}
            if method == 'POST' and path == '/deal/42/comments': return {'data': {'id': '17'}}
            self.fail(f'Unexpected mutation {method} {path}')
        api._call.side_effect = call
        api.upload_file.return_value = {'id': '7'}
        return api

    def test_publish_reused_and_no_deal_creation(self):
        api = self.api()
        with patch.object(kp, 'render', side_effect=lambda data, path: path.write_bytes(b'pdf')):
            first = kp.publish('42', api, recipient='Татьяна')
            second = kp.publish('42', api, recipient='Татьяна')
        self.assertEqual(first['fingerprint'], second['fingerprint'])
        self.assertTrue(second['reused'])
        self.assertEqual(api.upload_file.call_count, 1)

    def test_concurrent_change_prevents_upload(self):
        api = self.api()
        count = 0
        original = api._call.side_effect
        def call(method, path, **kwargs):
            nonlocal count
            result = original(method, path, **kwargs)
            if path == '/deal/42':
                count += 1
                if count == 2: result['data']['description'] = 'Изменилось'
            return result
        api._call.side_effect = call
        with patch.object(kp, 'render'), self.assertRaisesRegex(ValueError, 'изменилась'):
            kp.publish('42', api, recipient='Татьяна')
        api.upload_file.assert_not_called()

    def test_bootstrap_does_not_publish_existing_deals(self):
        with patch('deal_browser.fetch_all', return_value=[example()]), patch.object(kp, 'publish') as publish:
            self.assertEqual(kp.scan(Mock())['results'], [])
            publish.assert_not_called()

    def test_transition_asks_recipient_without_generating_then_ack(self):
        before = example(); before['state'] = {'id': '129'}
        api = self.api()
        with patch('deal_browser.fetch_all', return_value=[before]): kp.scan(api)
        with patch('deal_browser.fetch_all', return_value=[example()]), patch.object(kp, 'publish') as publish:
            r = kp.scan(api)['results'][0]
            self.assertTrue(r['needs_recipient'])
            publish.assert_not_called()
            kp.ack('42', r['event'])
            self.assertEqual(kp.scan(api)['results'], [])

    def test_recipient_required_before_api_calls(self):
        api = self.api()
        with self.assertRaisesRegex(ValueError, 'кому адресовать'):
            kp.publish('42', api)
        api._call.assert_not_called()

    def test_different_recipient_is_new_version(self):
        api = self.api()
        original = api._call.side_effect
        api._call.side_effect = lambda method, path, **kw: {'data': {'id': '17'}} if path == '/comment/17' else original(method, path, **kw)
        with patch.object(kp, 'render', side_effect=lambda data, path: path.write_bytes(b'pdf')):
            first = kp.publish('42', api, recipient='Татьяна')
            second = kp.publish('42', api, recipient='Иван')
        self.assertNotEqual(first['fingerprint'], second['fingerprint'])

    def test_new_version_never_edits_old_comment_or_trips_breaker(self):
        api = self.api()
        original = api._call.side_effect
        def call(method, path, **kwargs):
            if method == 'POST' and path == '/comment/17':
                raise AssertionError('Editing the old comment would trip the shared 403 breaker')
            return original(method, path, **kwargs)
        api._call.side_effect = call
        with patch.object(kp, 'render', side_effect=lambda data, path: path.write_bytes(b'pdf')):
            kp.publish('42', api, recipient='Татьяна')
            result = kp.publish('42', api, recipient='Юрий Андреевич')
            again = kp.publish('42', api, recipient='Юрий Андреевич')
        self.assertTrue(result['ok'])
        self.assertTrue(again['reused'])
        self.assertEqual(api.upload_file.call_count, 2)
        posts = [c for c in api._call.call_args_list if c.args == ('POST', '/deal/42/comments')]
        self.assertEqual(len(posts), 2)
        self.assertNotIn('id', posts[-1].kwargs['json_body'])

    def test_unconfirmed_attachment_is_not_reported_successful(self):
        api = self.api(); original = api._call.side_effect
        api._call.side_effect = lambda method, path, **kw: {'data': []} if path.endswith('/allFiles') else original(method, path, **kw)
        with patch.object(kp, 'render', side_effect=lambda data, path: path.write_bytes(b'pdf')):
            with self.assertRaisesRegex(ValueError, 'не подтвердил'):
                kp.publish('42', api, recipient='Юрий')
            with self.assertRaisesRegex(ValueError, 'не подтвердил'):
                kp.publish('42', api, recipient='Юрий')
        api.upload_file.assert_called_once()


if __name__ == '__main__':
    unittest.main()
