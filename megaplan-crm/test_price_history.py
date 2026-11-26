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
        self.assertEqual(1500, sell)                      # owner 24.11: fittings at +200 %
        self.assertIn('Галвент счёт 77', mark); self.assertIn('наценка на фасонку 200%', mark)
        sell, cost, mark = ph.price_from_history('Отвод 90 градусов Ø250 оцинкованный', self.rows, ratios, fitting_markup=3.5)
        self.assertEqual(1750, sell)

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
        dump({'invoices': [{'supplier': 'Вентрешения', 'number': '40', 'lines': [
            {'name': 'Воздуховод(Пр) - 300x400 - 1250', 'qty': 1, 'unit': 'шт', 'amount_cents': 175000},
            {'name': 'Воздуховод(Пр) - 300x500 - 1250', 'qty': 1, 'unit': 'шт', 'amount_cents': 200000},
            {'name': 'Воздуховод 400x600', 'qty': 1, 'unit': 'м2', 'amount_cents': 100000},
        ]}]}, self.registry)
        rows = ph.load_history(self.offers, self.registry, self.index)
        sell, cost, mark = ph.price_from_history('Воздуховод оцинкованный 0,5 мм, 400×150 мм, Галвент', rows,
                                                 {'группа:воздуховод': 1.5})
        # ₽ per m² of surface: 1750/1.25/1.4 = 1000, 2000/1.25/1.6 = 1000, 1000 per м² → 1000 × 1.1 m²/m
        self.assertEqual(1100.0, cost)
        self.assertEqual(1650.0, sell)
        self.assertIn('по периметру сечения из 3', mark)

    def test_past_deal_rows_without_a_unit_do_not_price_rectangular_ducts(self):
        """TASK-20261126-03: unit-less past-deal prices (often per m²) gave rectangular ducts at 3–4× the invoice."""
        dump({'offers': [{'id': i, 'name': f'Воздуховод(Пр) - {a}x{b} - 1250', 'price': 9000}
                         for i, (a, b) in enumerate(((300, 400), (300, 500), (400, 600)), 1)]}, self.offers)
        rows = ph.load_history(self.offers, self.registry, self.index)
        self.assertIsNone(ph.rect_duct_estimate('Воздуховод оцинкованный 0,5 мм, 400×150 мм', rows, {'группа:воздуховод': 1.5}))

    def test_services_never_price_goods(self):
        self.assertEqual(0.0, ph.similarity('Наружный блок mini-VRV Daikin 4MXM68N', 'ТО внешнего блока VRV системы'))

    def test_other_kinds_without_own_markup_use_the_ventilation_markup(self):
        ratios = {'группа:воздуховод': 1.4}
        dump({'invoices': [{'supplier': 'Галвент', 'number': '9', 'lines': [
            {'name': 'Дроссель-клапан ф125', 'qty': 10, 'unit': 'шт', 'amount_cents': 200000}]}]}, self.registry)
        rows = ph.load_history(self.offers, self.registry, self.index)
        sell, cost, mark = ph.price_from_history('Дроссель-клапан оцинкованный ДК Ø125 мм, Галвент', rows, ratios)
        self.assertEqual((280.0, 200.0), (sell, cost))
        self.assertIn('вентиляционные изделия', mark)

    def test_missing_fitting_is_priced_by_area_from_ventresheniya(self):
        import fitting_area
        lines = [{'name': n, 'qty': 1, 'unit': 'шт', 'amount_cents': round(fitting_area.area(n) * 2000 * 100)}
                 for n in ('Отвод(Кр) - 90 - 160', 'Отвод(Кр) - 45 - 200', 'Ниппель(Кр) - 200', 'Отвод(Кр) - 90 - 250')]
        dump({'invoices': [{'supplier': 'ООО Вентрешения', 'number': '31', 'lines': lines}]}, self.registry)
        rows = ph.load_history(self.offers, self.registry, self.index)
        sell, cost, mark = ph.price_from_history('Отвод оцинкованный 45°, Ø125 мм, Галвент', rows, {})
        expected = round(fitting_area.area('Отвод оцинкованный 45°, Ø125 мм') * 2000, 2)
        self.assertEqual((round(expected * 3, 2), expected), (sell, cost))
        self.assertIn('расчёт по площади', mark); self.assertIn('Вентрешения', mark)

    def test_rectangular_piece_without_length_is_1250_and_round_is_3000(self):
        self.assertEqual(1250, ph.duct_length('Воздуховод 400×150', 'Воздуховод прямоугольный 400х150 оц', 'шт'))
        self.assertEqual(3000, ph.duct_length('Воздуховод Ø160', 'Воздуховод d160', 'шт'))
        self.assertIsNone(ph.duct_length('Воздуховод Ø160', 'Воздуховод d160', 'м'))

    def test_dollar_catalog_price_is_converted_never_read_as_roubles(self):
        dump({'offers': [{'id': 5, 'name': 'PNM Наконечник форсунки 85 мкм', 'price': 12, 'price_currency': 'USD',
                          'cost_material': 8, 'cost_currency': 'USD'}]}, self.offers)
        rows = ph.load_history(self.offers, self.registry, self.index, rate=lambda code: 82.0 if code == 'USD' else None)
        sell, cost, mark = ph.price_from_history('Наконечник форсунки Liechty PNM, отверстие 85 мкм', rows, {})
        self.assertEqual((984.0, 656.0), (sell, cost))
        self.assertIn('USD пересчитана по курсу ЦБ', mark)
        rows = ph.load_history(self.offers, self.registry, self.index, rate=lambda code: None)
        self.assertIsNone(ph.price_from_history('Наконечник форсунки Liechty PNM, отверстие 85 мкм', rows, {}))

    def test_a_named_model_needs_the_same_model(self):
        """Deal 907: indoor FXSQ20A got the price of an outdoor VRV set that named no model."""
        self.assertEqual(0.0, ph.similarity('Внутренний канальный блок mini-VRV Daikin FXSQ20A',
                                            'Внутренний блок VRV Daikin (комплект системы)'))
        self.assertGreater(ph.similarity('Внутренний канальный блок mini-VRV Daikin FXSQ32A',
                                         'Внутренний блок канального типа DAIKIN FXSQ32A'), 0.5)

    def test_sale_price_without_cost_takes_the_cost_from_a_purchase(self):
        dump({'offers': [{'id': 7, 'name': 'Ниппель Ф 160', 'price': 300}]}, self.offers)
        dump({'invoices': [{'supplier': 'Галвент', 'number': '12', 'lines': [
            {'name': 'Ниппель оцинк. d160', 'qty': 10, 'unit': 'шт', 'amount_cents': 180000}]}]}, self.registry)
        rows = ph.load_history(self.offers, self.registry, self.index)
        sell, cost, mark = ph.price_from_history('Ниппель оцинкованный Ø160 мм, Галвент', rows, {})
        self.assertEqual((300, 180.0), (sell, cost))
        self.assertIn('закупка — Галвент счёт 12', mark)

    def test_nothing_similar_gives_nothing(self):
        self.assertIsNone(ph.price_from_history('Наконечник форсунки Liechty PNM 85 мкм', self.rows, ph.markups(self.rows)))


if __name__ == '__main__':
    unittest.main()
