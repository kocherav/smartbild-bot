import unittest

from deal_browser import natural_match_score, stem_match_score


class DealNaturalSearchTest(unittest.TestCase):
    def test_short_phrase(self):
        self.assertGreater(natural_match_score('JetCar', 'Автосалон JetCar'), 0)

    def test_very_long_phrase_finds_object(self):
        phrase = ('Покажи мне текущую сделку, где объект Павелецкая Сити, '
                  'и сразу скажи статус, сумму и кто исполнитель')
        self.assertGreater(natural_match_score(phrase, 'Павелецкая Сити'), 100)

    def test_unrelated_generic_prose_does_not_match(self):
        self.assertEqual(natural_match_score('покажи объект и статус', 'Автосалон JetCar'), 0)


    def test_case_endings_match_by_stem(self):
        value = 'Вентиляция склада ООО Альфа Климат Химки, Заводская 3'
        self.assertEqual(natural_match_score('складу в Химках', value), 0)
        self.assertEqual(stem_match_score('складу в Химках', value), 2)

    def test_stem_needs_a_meaningful_word(self):
        self.assertEqual(stem_match_score('по в на', 'Павелецкая Сити'), 0)
        self.assertEqual(stem_match_score('бассейну в Сочи', 'Вентиляция склада Химки'), 0)


if __name__ == '__main__':
    unittest.main()
