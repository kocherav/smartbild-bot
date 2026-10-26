"""Owner-approved improvements (QA_IDEAS.md И-1, И-2, И-4, И-5), checked as a person uses them."""
import unittest
from unittest.mock import patch

import bridge
from human_qa_harness import HumanJourneyCase, press, say
from test_human_journeys import DEAL, office


class QuickActionJourneys(HumanJourneyCase, unittest.TestCase):
    def test_welcome_offers_one_input_free_deal_search(self):
        def menu_journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('📍 Найти по адресу')
            yield say('Химки')
            person.sees('№990002', 'Склад', expected='Кнопочный маршрут нашёл сделку')

        before = self.play(menu_journey, setup=office)
        self.assertEqual(4, before.receipt()['actions'], 'до результата через меню — 4 действия')

        def free_text_journey(person):
            yield say('/start')
            person.sees('Можно написать задачу своими словами',
                        'найди сделку по складу в Химках',
                        expected='На старте видна подсказка о свободном вводе с примером')
            yield say('найди сделку по складу в Химках')
            person.sees('№990002', 'Склад', expected='Свободный запрос нашёл ту же сделку')

        after = self.play(free_text_journey, setup=office)
        self.assertEqual(1, after.receipt()['actions'] - 1,
                         'после приветствия до результата — один свободный ввод')
        self.assertEqual(0, len(after.model.prompts), 'Поиск сделки не должен уходить в ИИ')

    def test_number_alone_opens_the_deal_and_invoice_takes_four_actions(self):
        def journey(person):
            yield say('990001')
            person.sees('Сделка №990001', expected='Номер без меню открыл карточку (И-2)')
            person.sees_button('🧾 Выставить счёт', expected='Быстрые действия в карточке (И-1)')
            yield press('🧾 Выставить счёт')
            yield press('📋 Общий счёт по спецификации')
            yield press('✅ Выставить общий счёт')
            person.got_document('Счёт')
        stand = self.play(journey, setup=office)
        self.assertEqual(4, stand.receipt()['actions'], 'от номера до счёта — 4 действия вместо 8')
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create_full']))
        self.assertEqual(0, len(stand.model.prompts))

    def test_number_is_an_answer_when_the_bot_asked_for_it(self):
        def journey(person):
            yield say('Нужно сменить плательщика')
            yield say('990001')
            person.sees('Выберите нового плательщика', expected='Номер ушёл в заданный вопрос, а не в карточку')
        self.play(journey, setup=office)

    def test_number_after_an_assistant_turn_stays_in_that_conversation(self):
        def journey(person):
            yield say('Подбери кондиционер для серверной, нужен номер сделки?')
            yield say('990001')
            person.not_sees('Сделка №990001\nСуть', expected='Номер в разговоре с ассистентом не перехвачен')
        stand = self.play(journey, setup=office, model_rules=[('', 'Назовите номер сделки.')])
        self.assertEqual(2, len(stand.model.prompts))

    def test_quick_payer_and_status_buttons(self):
        def journey(person):
            yield say('990001')
            yield press('🏢 Сменить плательщика')
            person.sees_button('ООО «Альфа Климат» · ИНН 7701000001 · ✓ текущий',
                               expected='В списке ИНН и отметка текущего плательщика (И-5)')
            yield press('ООО «Альфа Сервис» · ИНН 7701000002')
            yield press('✅ Сменить плательщика')
            person.sees('Дальше: «🧾 Выставить счёт»', expected='После смены плательщика бот подсказал следующий шаг (И-4)')
            yield press('🔄 Изменить статус')
            person.sees('Куда перевести сделку')
        stand = self.play(journey, setup=office)
        self.assertEqual('7102', stand.crm.deals[DEAL]['payer_id'])

    def test_payer_by_inn_in_a_phrase(self):
        def journey(person):
            yield say('Поменяй плательщика в сделке 990001 на ИНН 7701000002')
            person.sees('Новый плательщик: ООО «Альфа Сервис», ИНН 7701000002')
        self.play(journey, setup=office)


    def test_executor_from_the_deal_card(self):
        def journey(person):
            yield say('990001')
            yield press('👤 Назначить исполнителя')
            person.sees('Кого назначить исполнителем сделки №990001', expected='Кнопка в карточке спросила, кого назначить')
            yield say('Смирнов')
            yield press('Сотрудник ID 1000011 — Алексей Смирнов')
            yield press('✅ Назначить исполнителя')
        stand = self.play(journey, setup=office)
        self.assertEqual(['Алексей Смирнов'], stand.crm.deals[DEAL]['executors'])
        self.assertEqual(5, stand.receipt()['actions'], 'от номера до назначения — 5 действий вместо 12+')
        self.assertEqual(0, len(stand.model.prompts))

    def test_counted_deal_list_by_phrase_is_pressable(self):
        def journey(person):
            yield say('Покажи 1 сделку с Альфа Климат')
            person.sees('показаны последние 1 из 2', expected='Бот показал столько сделок, сколько просили')
            person.sees_button('№990002 · Вентиляция склада', expected='Каждая сделка списка — кнопка')
            yield press('№990002 · Вентиляция склада')
            person.sees('Сделка №990002', expected='Нажатие сразу открыло карточку')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(stand.model.prompts), 'Список сделок по фразе не должен уходить в ИИ')

    def test_assistant_list_of_deals_gets_buttons(self):
        listing = ('Нашёл такие сделки:\n\n1. №990001 — Кондиционирование офиса\n   Этап: Заявка\n\n'
                   '2. №990002 — Вентиляция склада\n   Этап: Закупка\n\nСчёт №311 — выставлен.')
        def journey(person):
            yield say('Какие у нас сейчас интересные объекты?')
            person.sees_button('№990002 · Вентиляция склада', expected='Список сделок от ассистента — с кнопками')
            yield press('№990002 · Вентиляция склада')
            person.sees('Сделка №990002', expected='Кнопка открыла сделку без «открой карточку 990002»')
        self.play(journey, setup=office, model_rules=[('интересные объекты', listing)])

class EdoOfferJourneys(HumanJourneyCase, unittest.TestCase):
    def issue(self, person):
        yield say('990001')
        yield press('🧾 Выставить счёт')
        yield press('📋 Общий счёт по спецификации')
        yield press('✅ Выставить общий счёт')

    def test_edo_is_offered_and_sent_only_by_the_button(self):
        sent = []
        def journey(person):
            yield from self.issue(person)
            person.sees('отправить договор и этот счёт Татьяне', 'Без нажатия ничего не отправляется',
                        expected='После счёта предложена отправка по ЭДО (И-4)')
            person.check('До нажатия ничего не отправлено', sent, not sent)
            yield press('📤 Отправить по ЭДО')
            person.sees('отправлены Татьяне')
        with patch.object(bridge, 'dispatch_edo_documents',
                          side_effect=lambda token, deal, ids, force=False: sent.append((deal, ids)) or {'ok': True}):
            stand = self.play(journey, setup=office)
        new_invoice = next(i for i in stand.crm.invoices.values() if i['number'] != '311')
        self.assertEqual([(DEAL, [new_invoice['id']])], sent)

    def test_already_sent_bundle_is_not_resent(self):
        def journey(person):
            yield from self.issue(person)
            yield press('📤 Отправить по ЭДО')
            person.sees('уже отправлялись', 'Повторно не отправляю')
        with patch.object(bridge, 'dispatch_edo_documents', return_value={'ok': True, 'skipped': True}):
            self.play(journey, setup=office)

    def test_edo_failure_is_reported_honestly(self):
        def journey(person):
            yield from self.issue(person)
            yield press('📤 Отправить по ЭДО')
            person.sees('не отправлен', 'Татьяна не зарегистрирована')
        self.play(journey, setup=office)


if __name__ == '__main__':
    unittest.main()
