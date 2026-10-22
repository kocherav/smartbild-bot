import unittest

import megaplan_api


class NaturalContractorQueryTest(unittest.TestCase):
    def test_brand_survives_conversational_suffix(self):
        requested = megaplan_api.meaningful_contractor_tokens(
            'JetCAr со следующими позициями')
        stored = megaplan_api.meaningful_contractor_tokens('Автосалон JetCar')
        self.assertEqual({'jetcar'}, requested & stored)

    def test_generic_words_alone_do_not_match(self):
        requested = megaplan_api.meaningful_contractor_tokens('клиент организация')
        stored = megaplan_api.meaningful_contractor_tokens('Автосалон JetCar')
        self.assertFalse(requested & stored)

    def test_long_sentence_yields_embedded_name_variants(self):
        variants = megaplan_api.natural_name_fragments(
            'Создай новую сделку в клиенте Автосалон JetCar со следующими двадцатью позициями')
        self.assertIn('JetCar', variants)
        self.assertNotIn('Автосалон', variants)


if __name__ == '__main__':
    unittest.main()
