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
        self.index = os.path.join(self.dir, 'index.json')
        dump([], self.index)
        self.rows = ph.load_history(self.offers, self.registry, self.index)

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
        rows = [r for r in ph.load_history(self.offers, self.registry, self.index) if r['source'] == 'счёт поставщика']
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

    def test_supplier_invoice_text_rows_feed_history_and_ducts_are_priced_per_metre(self):
        text = """Счет на оплату № 1234 от 12 октября 2026 г.
Поставщик: ООО "Галвент", ИНН 7701234567
 1  Воздуховод круглый оцинк. d125 L=1250      10      шт    450,00      4 500,00
 2  Отвод 90 гр d315 оцинк                      6       шт    310,50      1 863,00
                                               Итого:                     6 363,00
"""
        dump([{'path': '/deals/880/galvent_1234.pdf', 'text': text}], self.index)
        rows = ph.load_history(self.offers, self.registry, self.index)
        ratios = {'воздуховод': 1.5, 'отвод': 1.6}
        sell, cost, mark = ph.price_from_history('Воздуховод оцинкованный 0,5 мм, Ø125 мм, Галвент', rows, ratios)
        self.assertEqual(360.0, cost)                       # 450 ₽ per 1.25 m piece
        self.assertEqual(540.0, sell)
        self.assertIn('пересчитано за 1 м', mark); self.assertIn('galvent_1234.pdf', mark)
        sell, cost, mark = ph.price_from_history('Отвод оцинкованный 90°, Ø315 мм, Галвент', rows, ratios)
        self.assertEqual(310.5, cost)

    def test_rectangular_duct_size_never_bought_is_estimated_by_perimeter(self):
        offers = {'offers': [
            {'id': 1, 'name': 'Воздуховод(Пр) - 300x400 - 1250 (оц. ст. 0.50/100 - Шина R20х95О)', 'price': 2800},
            {'id': 2, 'name': 'Воздуховод(Пр) - 300x500 - 1250 (оц. ст. 0.70/100 - Шина R20х95О)', 'price': 3200},
            {'id': 3, 'name': 'Воздуховод(Пр) - 400x600 - 1250 (оц. ст. 0.80/100)', 'price': 4000},
        ]}
        dump(offers, self.offers)
        rows = ph.load_history(self.offers, self.registry, self.index)
        sell, cost, mark = ph.price_from_history('Воздуховод оцинкованный 0,5 мм, 400×150 мм, Галвент', rows, {})
        # per metre per metre of perimeter: 2800/1.25/1.4=1600, 3200/1.25/1.6=1600, 4000/1.25/2.0=1600
        self.assertEqual(round(1600 * 1.1, 2), sell)
        self.assertIn('по периметру сечения из 3', mark)

    def test_services_never_price_goods(self):
        self.assertEqual(0.0, ph.similarity('Наружный блок mini-VRV Daikin 4MXM68N', 'ТО внешнего блока VRV системы'))

    def test_fittings_without_own_markup_use_the_ventilation_markup(self):
        ratios = {'группа:воздуховод': 1.4}
        dump({'invoices': [{'supplier': 'Галвент', 'number': '9', 'lines': [
            {'name': 'Ниппель Ф 125', 'qty': 10, 'unit': 'шт', 'amount_cents': 20000}]}]}, self.registry)
        rows = ph.load_history(self.offers, self.registry, self.index)
        sell, cost, mark = ph.price_from_history('Ниппель оцинкованный Ø125 мм, Галвент', rows, ratios)
        self.assertEqual((28.0, 20.0), (sell, cost))
        self.assertIn('вентиляционные изделия', mark)

    def test_rectangular_piece_without_length_is_1250_and_round_is_3000(self):
        self.assertEqual(1250, ph.duct_length('Воздуховод 400×150', 'Воздуховод прямоугольный 400х150 оц', 'шт'))
        self.assertEqual(3000, ph.duct_length('Воздуховод Ø160', 'Воздуховод d160', 'шт'))
        self.assertIsNone(ph.duct_length('Воздуховод Ø160', 'Воздуховод d160', 'м'))

    def test_nothing_similar_gives_nothing(self):
        self.assertIsNone(ph.price_from_history('Наконечник форсунки Liechty PNM 85 мкм', self.rows, ph.markups(self.rows)))


if __name__ == '__main__':
    unittest.main()
