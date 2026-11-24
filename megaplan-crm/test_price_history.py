"""Owner 24.11: prices from earlier deals and supplier invoices, matched loosely but safely."""
import json
import os
import tempfile
import unittest

import price_history as ph


def dump(obj, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False)


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
        dump({'offers': [
            {'id': 100, 'name': 'Диффузор щелевой 2 щели 1000 мм 15 мм', 'price': 5000, 'cost_material': 3000},
            {'id': 200, 'name': 'щелевой диффузор 2 щели L1000 щель 15', 'price': 5400, 'cost_material': 3200},
            {'id': 300, 'name': 'Отвод 90 Ø125', 'price': 400, 'cost_material': 250},
            {'id': 301, 'name': 'Отвод 90 Ø160', 'price': 500, 'cost_material': 300},
            {'id': 302, 'name': 'Отвод 90 Ø200', 'price': 640, 'cost_material': 400},
        ]}, self.offers)
        dump({'invoices': [{'supplier': 'Галвент', 'number': '77', 'date': '2026-09-01', 'allocations': [
            {'deal_id': '880', 'source_lines': [{'source_name': 'Отвод 90° ф250 оцинк', 'source_qty': 4, 'amount_used': 2000}]}]}]}, self.registry)
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

    def test_invoice_lines_in_the_canonical_registry_are_read(self):
        dump({'invoices': [{'supplier': 'Галвент', 'number': '81', 'lines': [
            {'name': 'Ниппель 125 оц', 'qty': 10, 'amount_cents': 150000}]}]}, self.registry)
        rows = [r for r in ph.load_history(self.offers, self.registry) if r['source'] == 'счёт поставщика']
        self.assertEqual([('Ниппель 125 оц', 150.0)], [(r['name'], r['cost']) for r in rows])

    def test_dry_run_false_matches_are_refused(self):
        """TASK-20261124-05 on deal 907: these pairs were offered and are wrong."""
        for a, b in [('Внутренний канальный блок mini-VRV Daikin FXSQ20A', 'Внутренний настенный блок Daikin FXAQ20A'),
                     ('Диффузор щелевой Invisiline SMART-40-B-2000-2', 'Диффузор щелевой Invisiline AESTH-40-B-2000-2'),
                     ('Проводной/беспроводной пульт Liechty HS4-N',
                      'Фанкойл канальный Carrier 4-х трубный в комплекте с клапанными узлами и проводным пультом'),
                     ('Диффузор вытяжной круглый AirGlass 125', 'Диффузор вентиляционный круглый ДВК 125')]:
            with self.subTest(a=a):
                self.assertEqual(0.0, ph.similarity(a, b))

    def test_dry_run_misses_now_match(self):
        for a, b in [('Воздуховод оцинкованный 0,5 мм, Ø125 мм, Галвент', 'Воздуховод круглый оц. 125'),
                     ('Тройник оцинкованный Ø125–Ø125 мм, Галвент', 'Тройник 125'),
                     ('Отвод оцинкованный 90°, Ø125 мм, Галвент', 'Отвод 90 гр d125 оцинк')]:
            with self.subTest(a=a):
                self.assertGreaterEqual(ph.similarity(a, b), ph.MIN_SIMILARITY)

    def test_nothing_similar_gives_nothing(self):
        self.assertIsNone(ph.price_from_history('Наконечник форсунки Liechty PNM 85 мкм', self.rows, ph.markups(self.rows)))


if __name__ == '__main__':
    unittest.main()
