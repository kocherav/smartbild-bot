"""Human route for finding an already issued invoice without knowing its number."""
import unittest

from human_qa_harness import HumanJourneyCase, press, say
from test_human_journeys import office


class ExistingInvoiceDiscoveryJourney(HumanJourneyCase, unittest.TestCase):
    def test_money_menu_points_to_deal_search(self):
        def before(person):
            # The observed route: the manager checks Money twice, then guesses
            # that the invoice may be hidden in the deal card.
            yield press('🏦 Деньги')
            yield press('⬅️ Главное меню')
            yield press('🏦 Деньги')
            yield press('⬅️ Главное меню')
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('🔎 Найти по клиенту')
            yield say('Альфа Климат')
            yield press('№990001 · Кондиционирование офиса на Тверской')
            yield press('📥 Получить счёт')
            person.got_document('311', expected='Существующий счёт найден через карточку сделки')

        old_route = self.play(before, setup=office)
        self.assertEqual(10, old_route.receipt()['actions'], 'наблюдавшийся маршрут занимал 10 действий')

        def after(person):
            yield press('🏦 Деньги')
            person.sees('Нужен уже выставленный счёт?', 'клиенту или адресу',
                        expected='Раздел Деньги объясняет, где искать существующий счёт')
            person.sees_button('🔎 Найти сделку', expected='Из подсказки можно сразу перейти к поиску')
            yield press('🔎 Найти сделку')
            yield press('🔎 Найти по клиенту')
            yield say('Альфа Климат')
            yield press('№990001 · Кондиционирование офиса на Тверской')
            yield press('📥 Получить счёт')
            person.got_document('311', expected='Подсказка довела до существующего счёта')

        new_route = self.play(after, setup=office)
        self.assertEqual(6, new_route.receipt()['actions'], 'новый заметный маршрут занимает 6 действий')
        self.assertEqual([], new_route.crm.writes, 'поиск и получение счёта работают только на чтение')
        self.assertEqual(0, len(new_route.model.prompts), 'маршрут не зависит от ИИ')


if __name__ == '__main__':
    unittest.main()
