"""Owner 24.11: prices from earlier deals and supplier invoices, matched loosely but safely."""
import json
import os
import tempfile
import unittest

import price_history as ph


class LooseButSafeMatching(unittest.TestCase):
    def test_same_item_written_differently_matches(self):
        for a, b in [("Диффузор щелевой 2-щелевой L=1000 щель 15мм", "щелевой диффузор, 2 щели, 1000 мм, 15 мм, белый"),
                     ("Переход оцинкованный 400×150–300×150 мм, Галвент", "Переход 400х150/300х150 оцинк."),
                     ("Тройник оцинкованный Ø125–Ø125 мм, Галвент", "Тройник ф125-125"),
                     ("Воздуховод круглый Ø160 L=1м", "воздуховод d160 1000мм")]:
            with self.subTest(a=a):
                self.assertGreaterEqual(ph.similarity(a, b), ph.MIN_SIMILARITY)

    def test_other_size_material_shape_or_kind_never_matches(self):
        for a, b in [("Диффузор щелевой 2 щели L=1000 щель 15мм", "Диффузор щелевой 3 щели 1000 мм 15 мм"),
                     ("Ниппель оцинкованный Ø125 мм", "Ниппель 160"),
                     ("Переход оцинкованный 400×150–300×150", "Переход нерж 400х150/300х150"),
                     ("Воздуховод круглый Ø160 L=1м", "воздуховод прямоугольный 160 1000мм"),
                     ("Тройник Ø125", "Отвод Ø125")]:
            with self.subTest(a=a):
                self.assertEqual(0.0, ph.similarity(a, b))


class HistorySources(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.offers = os.path.join(self.dir, 'offers.json')
        self.registry = os.path.join(self.dir, 'registry.json')
        json.dump({'offers': [
            {'id': 100, 'name': 'Диффузор щелевой 2 щели 1000 мм 15 мм', 'price': 5000, 'cost_material': 3000},
            {'id': 200, 'name': 'щелевой диффузор 2 щели L1000 щель 15', 'price': 5400, 'cost_material': 3200},
            {'id': 300, 'name': 'Отвод 90 Ø125', 'price': 400, 'cost_material': 250},
            {'id': 301, 'name': 'Отвод 90 Ø160', 'price': 500, 'cost_material': 300},
            {'id': 302, 'name': 'Отвод 90 Ø200', 'price': 640, 'cost_material': 400},
        ]}, open(self.offers, 'w'))
        json.dump({'invoices': [{'supplier': 'Галвент', 'number': '77', 'date': '2026-09-01', 'allocations': [
            {'deal_id': '880', 'source_lines': [{'source_name': 'Отвод 90° ф250 оцинк', 'source_qty': 4, 'amount_used': 2000}]}]}]},
                  open(self.registry, 'w'))
        self.rows = ph.load_history(self.offers, self.registry)

    def test_newest_sale_price_wins_and_is_marked(self):
        sell, cost, mark = ph.price_from_history('Диффузор щелевой двухщелевой, L=1000, щель 15 мм', self.rows)
        self.assertEqual((5400, 3200), (sell, cost))
        self.assertIn('проверить', mark); self.assertIn('номенклатура 200', mark)

    def test_supplier_invoice_price_gets_the_usual_markup_of_the_kind(self):
        ratios = ph.markups(self.rows)
        sell, cost, mark = ph.price_from_history('Отвод 90 градусов Ø250 оцинкованный', self.rows, ratios)
        self.assertEqual(500, cost)
        self.assertAlmostEqual(500 * ratios['отвод'], sell, places=1)
        self.assertIn('Галвент счёт 77', mark)

    def test_nothing_similar_gives_nothing(self):
        self.assertIsNone(ph.price_from_history('Наконечник форсунки Liechty PNM 85 мкм', self.rows, ph.markups(self.rows)))


if __name__ == '__main__':
    unittest.main()
