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
        result = pba.price_rows(rows, hogart=hogart, daichi=daichi, kemiks=lambda name: None, history=lambda name: None)
        got = [(r['unit_price'], r.get('price_source')) for r in result['items']]
        self.assertEqual([(95000, 'Hogart AS25S2SF3FA-B'), (41000, 'Daichi ECO07AN/LETTA07AN'),
                          (15000, None), (0, 'цена не найдена в каталогах')], got)
        self.assertEqual(70000, result['items'][0]['cost_material'])
        self.assertEqual((2, ['Труба медная 6,35']), (result['found'], result['missing']))

    def test_pipes_and_insulation_are_priced_by_kemiks_rules(self):
        rows = [{'name': 'Труба медная 9,52', 'qty': 5}]
        result = pba.price_rows(rows, hogart=lambda a: None, daichi=lambda a: None,
                                kemiks=lambda name: (700, 350) if 'Труба' in name else None,
                                history=lambda name: None)
        self.assertEqual((700, 'КЕМИКС', 350), (result['items'][0]['unit_price'], result['items'][0]['price_source'],
                                              result['items'][0]['cost_material']))

    def test_history_fills_what_catalogs_miss_and_is_marked_for_check(self):
        rows = [{'name': 'Диффузор щелевой 2 щели L=1000 щель 15 мм', 'qty': 4}]
        mark = 'проверить: цена из прошлых сделок (очень похоже: «щелевой диффузор 2 щели 1000 мм 15 мм», номенклатура 13106)'
        result = pba.price_rows(rows, hogart=lambda a: None, daichi=lambda a: None, kemiks=lambda n: None,
                                history=lambda n: (5200, 3100, mark))
        row = result['items'][0]
        self.assertEqual((5200, 3100, mark, True), (row['unit_price'], row['cost_material'], row['price_source'], row['price_needs_check']))
        self.assertEqual((1, 1, []), (result['found'], result['from_history'], result['missing']))

    def test_plain_words_are_not_taken_for_articles(self):
        self.assertEqual([], pba.candidates({'name': 'Монтаж кондиционера настенного'}))
        self.assertEqual(['X1', 'AS25'], pba.candidates({'name': 'AS25', 'sku': 'X1'}))


if __name__ == '__main__':
    unittest.main()
