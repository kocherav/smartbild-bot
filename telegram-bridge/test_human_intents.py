import unittest
import human_intents as h


class HumanIntentTests(unittest.TestCase):
    def assert_intent(self, text, name, deal=None, target=None):
        result = h.classify(text)
        self.assertIsNotNone(result, text)
        self.assertEqual(name, result.name, text)
        self.assertEqual(deal, result.deal_id, text)
        if target is not None:
            self.assertEqual(target, result.target, text)

    def test_create_deal_free_word_order(self):
        variants = (
            "Создай по этому счёту новую сделку для JetCar.",
            "Давай сделаем для клиента JetCar сделку на основании приложенного файла.",
            "Нужно завести сделку с клиентом JetCar, позиции возьми из спецификации.",
        )
        for text in variants:
            with self.subTest(text=text): self.assert_intent(text, h.CREATE_DEAL, target="JetCar")

    def test_payer_variants(self):
        for text in ("Давай поменяем плательщика в сделке №900",
                     "В 900 сделке нужно сменить плательщика"):
            with self.subTest(text=text): self.assert_intent(text, h.CHANGE_PAYER, "900")

    def test_installer_variants(self):
        for text in ("Давай заменим монтажника в сделке 861",
                     "По сделке №861 нужно поменять монтажника"):
            with self.subTest(text=text): self.assert_intent(text, h.CHANGE_INSTALLER, "861")

    def test_executor_variants(self):
        variants = ("Назначь исполнителя сделки №900",
                    "Давай поменяем исполнителя в 900 сделке")
        for text in variants:
            with self.subTest(text=text): self.assert_intent(text, h.ASSIGN_EXECUTOR, "900")

    def test_payment_variants(self):
        variants = ("Давай проверим, сколько у нас оплачено по сделке №900",
                    "Покажи поступившую оплату по 900 сделке",
                    "Какой остаток долга по сделке номер 900?")
        for text in variants:
            with self.subTest(text=text): self.assert_intent(text, h.CHECK_PAYMENT, "900")

    def test_economics_request_is_not_mistaken_for_payment(self):
        variants = (
            "Покажи прибыль и маржу по сделке 990001 и пришли расчёт",
            "Пришли экономику сделки №900",
            "Рассчитай рентабельность по сделке 861",
        )
        for text, deal in zip(variants, ("990001", "900", "861")):
            with self.subTest(text=text): self.assert_intent(text, h.GET_ECONOMICS, deal)

    def test_no_business_guess(self):
        for text in ("Доброе утро", "Покажи последние сделки", "Оплати счет"):
            with self.subTest(text=text): self.assertIsNone(h.classify(text))

    def test_human_word_order_corpus(self):
        cases = {
            "В 900-й сделке поменяй плательщика на ООО Ромашка": h.CHANGE_PAYER,
            "По сделке 900 нужен другой плательщик — ООО Ромашка": h.CHANGE_PAYER,
            "Сделай плательщиком ООО Ромашка в сделке №900": h.CHANGE_PAYER,
            "Замени в 861 сделке монтажника на Деревянко Сергея": h.CHANGE_INSTALLER,
            "По 861 сделке поставь Сергея Деревянко монтажником": h.CHANGE_INSTALLER,
            "Назначь исполнителем сделки №861 Деревянко Сергея": h.ASSIGN_EXECUTOR,
            "В сделке 861 исполнителем должен быть Деревянко Сергей": h.ASSIGN_EXECUTOR,
            "Что с оплатой по 900 сделке?": h.CHECK_PAYMENT,
            "Сколько денег пришло от клиента по сделке номер 900?": h.CHECK_PAYMENT,
            "Есть долг по 900-й сделке?": h.CHECK_PAYMENT,
            "Заведи для JetCar сделку по приложенному счету": h.CREATE_DEAL,
            "По этому счету нужна новая сделка на Автосалон JetCar": h.CREATE_DEAL,
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(expected, h.classify(phrase).name)


if __name__ == "__main__":
    unittest.main()
