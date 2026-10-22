import unittest

from deal_browser import natural_match_score


class DealNaturalSearchTest(unittest.TestCase):
    def test_short_phrase(self):
        self.assertGreater(natural_match_score('JetCar', 'Автосалон JetCar'), 0)

    def test_very_long_phrase_finds_object(self):
        phrase = ('Покажи мне текущую сделку, где объект Павелецкая Сити, '
                  'и сразу скажи статус, сумму и кто исполнитель')
        self.assertGreater(natural_match_score(phrase, 'Павелецкая Сити'), 100)

    def test_unrelated_generic_prose_does_not_match(self):
        self.assertEqual(natural_match_score('покажи объект и статус', 'Автосалон JetCar'), 0)


if __name__ == '__main__':
    unittest.main()
