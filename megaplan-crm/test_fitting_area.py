"""Owner 24.11: galvanised fittings priced by the area of metal."""
import math
import unittest

import fitting_area as fa


class Areas(unittest.TestCase):
    def test_development_formulas(self):
        self.assertAlmostEqual(math.pi * 0.125 * 0.125 * math.pi / 2, fa.area('Отвод 90° Ø125'), places=3)
        self.assertAlmostEqual(2 * 0.55 * 0.3 * math.pi / 4, fa.area('Отвод 45°, 400×150 мм'), places=3)
        self.assertAlmostEqual((2 * 0.55 + 2 * 0.45) / 2 * 0.3, fa.area('Переход 400×150–300×150 мм'), places=3)
        self.assertAlmostEqual(math.pi * 0.16 * 0.1, fa.area('Ниппель Ø160'), places=3)
        self.assertAlmostEqual(0.3 * 0.15 + 0.9 * 0.03, fa.area('Заглушка 300×150'), places=3)

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
