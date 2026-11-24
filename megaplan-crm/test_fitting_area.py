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

    def test_rate_needs_three_known_items_of_the_supplier(self):
        rows = [{'name': f'Отвод(Кр) - 90 - {d}', 'cost': fa.area(f'Отвод 90° Ø{d}') * 1800, 'ref': 'Вентрешения счёт 5'}
                for d in (125, 160, 200)]
        self.assertAlmostEqual(1800, fa.rates(rows)[('отвод', 'round')][0], places=0)
        self.assertEqual({}, fa.rates(rows[:2]))
        self.assertEqual({}, fa.rates([{**r, 'ref': 'Галвент'} for r in rows]))


if __name__ == '__main__':
    unittest.main()
