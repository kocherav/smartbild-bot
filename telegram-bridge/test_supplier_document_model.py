"""TASK-20261124-15: the real КП Liechty — OCR mixed price and quantity and merged two sets."""
import json
import unittest
from unittest.mock import patch

import deal_price_flow as flow
import supplier_document_model as sdm
from test_deal_price_flow import FakeIO

ANSWER = json.dumps({"kind": "kp", "supplier": "Liechty", "currency": "USD", "rows": [
    {"name": "SV Активный бесшумный клапан", "qty": 3, "unit": "шт", "price": 234.5, "amount": 703.5, "variant": "Вариант 1"},
    {"name": "HPH3T Крепления для трубопровода", "qty": 2, "unit": "уп", "price": 20, "amount": 40, "variant": "Вариант 1"},
    {"name": "HPH3T Крепления для трубопровода", "qty": 2, "unit": "уп", "price": 20, "amount": 40, "variant": "Вариант 2"},
    {"name": "HS4-N Проводной/беспроводной пульт", "qty": 2, "unit": "шт", "price": 539, "amount": 704, "variant": ""},
]})


class ModelReading(unittest.TestCase):
    def test_rows_must_add_up_and_variants_are_kept(self):
        doc = sdm.parse_answer("Вот таблица:\n" + ANSWER)
        self.assertEqual(('kp', 'USD'), (doc['kind'], doc['currency']))
        self.assertEqual(3, len(doc['rows']))
        self.assertEqual(['HS4-N Проводной/беспроводной пульт'], [r['name'] for r in doc['rejected']])
        self.assertEqual(['Вариант 1', 'Вариант 2'], doc['variants'])
        self.assertEqual(2, len(sdm.only_variant(doc, 'Вариант 1')['rows']))

    def test_garbage_answer_falls_back_to_text_parser(self):
        self.assertFalse(sdm.parse_answer('Не удалось прочитать файл')['ok'])
        io = FakeIO({'pending': 'deal_price_docs', 'price_docs': []})
        io.read_model = lambda path: sdm.parse_answer('ошибка модели')
        with patch.object(flow, 'run_sources', return_value={'ok': True, 'kind': 'invoice', 'rows': [
                {'name': 'Ниппель 125', 'qty': 2, 'unit': 'шт', 'price': 100, 'amount': 200}], 'file': 'x.pdf'}):
            flow.add_file(io, 1, io.state(1), '/tmp/x.pdf', 'py')
        self.assertEqual('разбор текста', io.st['price_docs'][0].get('reader') or 'разбор текста')
        self.assertEqual('deal_price_check', io.st['pending'])

    def test_owner_picks_the_variant_before_checking(self):
        io = FakeIO({'pending': 'deal_price_docs', 'price_docs': []})
        io.read_model = lambda path: sdm.parse_answer(ANSWER)
        flow.add_file(io, 1, io.state(1), '/tmp/D4055.pdf', 'py')
        self.assertEqual('deal_price_variant', io.st['pending'])
        flow.handle_text(io, 1, io.state(1), 'Вариант: Вариант 1', lambda d: [], 'py', lambda job: job())
        self.assertEqual('deal_price_check', io.st['pending'])
        self.assertEqual(2, len(io.st['price_docs'][0]['rows']))
        self.assertIn('3 × 234,50 $ = 703,50 $', io.sent[-1][0])
        self.assertIn('Не взято строк: 1', io.sent[-1][0])


if __name__ == '__main__':
    unittest.main()
