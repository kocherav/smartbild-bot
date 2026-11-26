"""Owner 24.11: galvanised fittings priced by the area of metal."""
import math
import unittest

import fitting_area as fa


class Areas(unittest.TestCase):
    def test_areas_match_the_suppliers_own_m2(self):
        """26.11: the Вентрешения invoice ПКБ-00005189 states each item's m² — every formula within 8 %."""
        supplier = [('Воздуховод Ф 125', 0.393, 1.0), ('Воздуховод 200 х 100 L=1250', 0.75, None),
                    ('Воздуховод 400 х 150 L=1250', 1.375, None), ('Дроссель-клапан Ф 125', 0.103, None),
                    ('Заглушка 300 х 150', 0.0725, None), ('Отвод круглый 45 Ф 125', 0.09, None),
                    ('Отвод круглый 90 Ф 125', 0.16, None), ('Отвод круглый 45 Ф 160', 0.14, None),
                    ('Отвод круглый 90 Ф 160', 0.25, None), ('Отвод 45 400 х 150 р.ш.150', 0.4117, None),
                    ('Отвод 90 400 х 150 р.ш.150', 0.71, None), ('Переход круглый Ф 160 /Ф 125', 0.1, None),
                    ('Переход Ф 125 / 200 х 100 L=300', 0.195, None), ('Переход Ф 125 / 300 х 100 L=300', 0.235, None),
                    ('Переход 400х150/300х150 L=300', 0.36, None), ('Тройник круглый Ф 125 /Ф 125', 0.205, None),
                    ('Тройник круглый Ф 160 /Ф 160', 0.28, None), ('Ниппель Ф 125', 0.03, None), ('Ниппель Ф 160', 0.04, None)]
        for name, m2, length in supplier:
            with self.subTest(name=name):
                self.assertLess(abs(fa.area(name, length) / m2 - 1), 0.08)

    def test_ventresheniya_names(self):
        self.assertEqual(fa.area('Отвод 90° Ø125'), fa.area('Отвод(Кр) - 90 - 125 (оц. ст. 0.50)'))
        vr = fa.parse_vr('Переход(ПрКр) - 1 - 400x300 - 315 - 334 - 25x34 (оц. ст. 0.50/100 - Шина R20х95О с ЖК)')
        self.assertEqual([('rect', 0.4, 0.3), ('round', 0.315)], vr['groups'])
        self.assertEqual(0.334, vr['length'])

    def test_rate_comes_from_the_nearest_sizes_of_the_supplier(self):
        """TASK-20261124-14: one median ₽/m² was 72–80 % low on small elbows (fixed cost per piece)."""
        names = [f'Отвод(Кр) - {a} - {d}' for a in (45, 90) for d in (100, 125, 160, 200, 250, 315)]
        rows = [{'name': n, 'cost': 150 + 1500 * fa.area(n), 'ref': 'Вентрешения счёт 5'} for n in names]
        table = fa.rates(rows)
        for q in ('Отвод оцинкованный 45°, Ø140 мм', 'Отвод 90° Ø180'):
            truth = 150 + 1500 * fa.area(q)
            self.assertLess(abs(fa.price(q, table)[1] - truth) / truth, 0.12, q)
        self.assertIsNone(fa.price('Отвод 90° Ø125', fa.rates(rows[:2])))
        self.assertEqual({}, fa.rates([{**r, 'ref': 'Галвент'} for r in rows]))

    def test_ducts_and_dampers_are_priced_by_area_too(self):
        """Deal 907: four rectangular ducts and a damper stayed at 0 ₽ while every fitting got a price."""
        import price_history as ph
        names = [f'Воздуховод(Пр) - {a}x{b} - 1250' for a, b in ((300, 400), (300, 500), (400, 600), (250, 200))] + \
                [f'Отвод(Кр) - 90 - {d}' for d in (100, 125, 160)]
        rows = [{'name': n, 'cost': 1200 * fa.area(n), 'ref': 'Вентрешения', 'price': None, 'source': 'счёт поставщика',
                 'order': 0} for n in names]
        sell, cost, mark = ph.fitting_estimate('Воздуховод оцинкованный 0,5 мм, 400×150 мм, Галвент', rows, 3.0,
                                               {'группа:воздуховод': 1.5})
        self.assertAlmostEqual(1.1 * 1200, cost, places=0)            # perimeter 1.1 m² per metre
        self.assertAlmostEqual(cost * 1.5, sell, places=1)
        self.assertIn('за 1 м', mark)
        self.assertIsNotNone(ph.fitting_estimate('Дроссель-клапан оцинкованный ДК Ø125 мм, Галвент', rows, 3.0, {}))


if __name__ == '__main__':
    unittest.main()
