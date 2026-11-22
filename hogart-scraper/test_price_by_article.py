"""Owner 22.11: a project without prices must still become a deal — prices from catalogs."""
import unittest

import price_by_article as pba


class PriceByArticleTests(unittest.TestCase):
    def test_rows_without_prices_are_priced_from_hogart_then_daichi_and_missing_stay_zero(self):
        hogart = {'AS25S2SF3FA-B': (95000, 70000)}.get
        daichi = {'ECO07AN/LETTA07AN': (41000, 30000)}.get
        rows = [{'name': 'Кондиционер Haier AS25S2SF3FA-B', 'qty': 2},
                {'name': 'Сплит Daichi ECO07AN/LETTA07AN', 'qty': 1, 'unit_price': ''},
                {'name': 'Монтаж', 'qty': 1, 'unit_price': 15000},
                {'name': 'Труба медная 6,35', 'qty': 10}]
        result = pba.price_rows(rows, hogart=hogart, daichi=daichi)
        got = [(r['unit_price'], r.get('price_source')) for r in result['items']]
        self.assertEqual([(95000, 'Hogart AS25S2SF3FA-B'), (41000, 'Daichi ECO07AN/LETTA07AN'),
                          (15000, None), (0, 'цена не найдена в каталогах')], got)
        self.assertEqual(70000, result['items'][0]['cost_material'])
        self.assertEqual((2, ['Труба медная 6,35']), (result['found'], result['missing']))

    def test_plain_words_are_not_taken_for_articles(self):
        self.assertEqual([], pba.candidates({'name': 'Монтаж кондиционера настенного'}))
        self.assertEqual(['X1', 'AS25'], pba.candidates({'name': 'AS25', 'sku': 'X1'}))


if __name__ == '__main__':
    unittest.main()
