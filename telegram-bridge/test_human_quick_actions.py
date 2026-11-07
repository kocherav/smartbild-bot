"""Owner-approved improvements (QA_IDEAS.md И-1, И-2, И-4, И-5), checked as a person uses them."""
import datetime as dt
import unittest
from unittest.mock import patch

import bridge
from human_qa_harness import HumanJourneyCase, press, say
from test_human_journeys import DEAL, office


class QuickActionJourneys(HumanJourneyCase, unittest.TestCase):
    def test_client_and_object_phrase_opens_unique_deal_before_invoice(self):
        def menu_journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('🔎 Найти по клиенту')
            yield say('Альфа Климат')
            yield press('№990001 · Кондиционирование офиса на Тверской')
            yield press('📥 Получить счёт')
            person.got_document('Счёт', expected='Получен счёт найденной сделки')

        before = self.play(menu_journey, setup=office)
        self.assertEqual(6, before.receipt()['actions'], 'до изменения — 6 действий до счёта')

        def phrase_journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            person.sees('найди сделку клиента Альфа Климат по офису на Тверской',
                        expected='На экране поиска виден пример целой фразы')
            yield say('найди сделку клиента Альфа Климат по офису на Тверской')
            person.sees('Сделка №990001', 'Тверская', expected='Единственное совпадение сразу открыто')
            person.sees_button('📥 Получить счёт')
            yield press('📥 Получить счёт')
            person.got_document('Счёт')

        after = self.play(phrase_journey, setup=office)
        self.assertEqual(2, after.receipt()['actions'] - 2,
                         'после входа в поиск — одно сообщение и одна кнопка')
        self.assertEqual(0, len(after.model.prompts), 'Поиск сделки не должен уходить в ИИ')

    def test_client_and_object_phrase_keeps_ambiguous_matches_as_a_list(self):
        def two_offices(crm):
            office(crm)
            crm.add_deal('990004', '501', 'Кондиционирование офиса на Тверской, 12', status_id='1',
                         address='Москва, Тверская ул., 12', payer_id='7101')

        def journey(person):
            yield say('найди сделку клиента Альфа Климат по офису на Тверской')
            person.sees('Найденные сделки', '№990001', '№990004',
                        expected='Неоднозначный поиск показал выбор, а не угадал сделку')
            person.not_sees('Сделка №990001\nСуть', expected='Карточка не открыта без выбора')

        self.play(journey, setup=two_offices)

    def test_welcome_offers_one_input_deal_number_search(self):
        def menu_journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('🔢 Найти по номеру')
            yield say('990001')
            person.sees('Сделка №990001', expected='Кнопочный маршрут открыл сделку')

        before = self.play(menu_journey, setup=office)
        self.assertEqual(4, before.receipt()['actions'],
                         'до результата через меню — 3 нажатия и ввод номера')

        def direct_journey(person):
            yield say('/start')
            person.sees('Просто отправьте номер сделки, например 990001',
                        expected='На старте видна подсказка о прямом поиске по номеру')
            yield say('990001')
            person.sees('Сделка №990001', expected='Номер со старта открыл ту же сделку')

        after = self.play(direct_journey, setup=office)
        self.assertEqual(1, after.receipt()['actions'] - 1,
                         'после приветствия до результата — один ввод')
        self.assertEqual(0, len(after.model.prompts), 'Прямой поиск не должен уходить в ИИ')

    def test_deals_section_prompts_for_one_message_number_search(self):
        def menu_journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('🔢 Найти по номеру')
            yield say(DEAL)
            person.sees(f'Сделка №{DEAL}', expected='Старый кнопочный маршрут по-прежнему работает')

        before = self.play(menu_journey, setup=office)
        self.assertEqual(4, before.receipt()['actions'], 'до результата через меню — 4 действия')

        def hinted_journey(person):
            yield press('🤝 Сделки')
            person.sees('Просто отправьте номер сделки — например, 990001',
                        expected='В разделе сделок видна подсказка о быстром вводе')
            yield say(DEAL)
            person.sees(f'Сделка №{DEAL}', expected='Номер открыл сделку одним сообщением после подсказки')

        after = self.play(hinted_journey, setup=office)
        self.assertEqual(1, after.receipt()['actions'] - 1,
                         'после входа в раздел до сделки — одно сообщение')
        self.assertEqual(0, len(after.model.prompts), 'Быстрый поиск по номеру не должен уходить в ИИ')

    def test_find_then_issue_invoice_keeps_the_original_intent(self):
        def journey(person):
            yield say('найди сделку Альфа кондиционирование офиса кабинет 103 и выстави по ней новый счёт сегодняшним числом')
            person.sees_button('№990001 · Кондиционирование офиса на Тверской',
                               expected='По описанию найден нужный объект, а кабинет 103 не принят за номер сделки')
            yield press('№990001 · Кондиционирование офиса на Тверской')
            person.sees('Выставить общий счёт по сделке №990001?', 'Дата:', 'ООО «Альфа Климат»', '114 000',
                        expected='Выбор сделки сразу открыл предпросмотр общего счёта')
            person.check('До единственной кнопки подтверждения записей нет', person.stand.crm.writes,
                         not person.stand.crm.writes)
            yield press('✅ Выставить общий счёт')
            person.got_document('Счёт')

        stand = self.play(journey, setup=office)
        self.assertEqual(3, stand.receipt()['actions'],
                         'после изменения — фраза, выбор сделки и обязательное подтверждение вместо пяти действий')
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create_full']))
        self.assertEqual(0, len(stand.model.prompts))

    def test_deals_menu_suggests_direct_executor_command(self):
        def menu_journey(person):
            yield press('🤝 Сделки')
            person.sees('Можно сразу написать:',
                        'назначь исполнителем сделки 990002 Алексея Смирнова',
                        expected='Меню сделок показывает готовый пример прямой команды')
            yield press('🔎 Найти сделку')
            yield press('🔢 Найти по номеру')
            yield say('990002')
            yield press('👤 Назначить исполнителя')
            yield say('Смирнов')
            yield press('Сотрудник ID 1000011 — Алексей Смирнов')
            yield press('✅ Назначить исполнителя')

        before = self.play(menu_journey, setup=office)
        self.assertEqual(8, before.receipt()['actions'], 'кнопочный маршрут — 8 действий')

        def direct_journey(person):
            yield say('назначь исполнителем сделки 990002 Алексея Смирнова')
            yield press('Сотрудник ID 1000011 — Алексей Смирнов')
            person.sees('Данные ещё не записаны', expected='Перед записью показан предпросмотр')
            yield press('✅ Назначить исполнителя')

        after = self.play(direct_journey, setup=office)
        self.assertEqual(3, after.receipt()['actions'], 'прямой маршрут — 3 действия')
        self.assertEqual(['Алексей Смирнов'], after.crm.deals['990002']['executors'])

    def test_welcome_offers_one_input_free_deal_search(self):
        def menu_journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield say('Химки')
            person.sees('№990002', 'Склад', expected='Кнопочный маршрут нашёл сделку')

        before = self.play(menu_journey, setup=office)
        self.assertEqual(3, before.receipt()['actions'], 'умный поиск через меню — 3 действия')

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

    def test_search_result_shows_amount_without_opening_deal(self):
        def journey(person):
            yield say('найди сделку по складу в Химках')
            person.sees('990002', 'Статус: Закупка', 'Сумма: 150 000',
                        expected='В результате поиска сразу видны статус и сумма сделки')

        stand = self.play(journey, setup=office)
        self.assertEqual(1, stand.receipt()['actions'],
                         'после изменения сумма видна за одно действие без открытия карточки')
        self.assertEqual([], stand.crm.writes, 'Поиск и просмотр суммы не изменяют CRM')

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

    def test_full_invoice_pdf_keeps_confirmed_date_and_current_status(self):
        def already_in_status_with_duplicate_transition(crm):
            office(crm)
            # Reproduces the QA payload: the card says the target status while
            # Megaplan still advertises a transition with the same display name.
            crm.statuses['99'] = 'Выставление счета'

        def journey(person):
            yield say('990001')
            yield press('🧾 Выставить счёт')
            yield press('📋 Общий счёт по спецификации')
            person.sees('Дата:', expected='Предпросмотр содержит закреплённую дату счёта')
            person.not_sees('Перевести её', expected='Уже установленный статус не записывается повторно')
            yield press('✅ Выставить общий счёт')
            person.got_document(dt.date.today().strftime('%d.%m.%Y'),
                                expected='PDF нового счёта имеет подтверждённую дату')
        stand = self.play(journey, setup=already_in_status_with_duplicate_transition)
        self.assertEqual([], [w for w in stand.crm.writes if w['action'] == 'move_status'])
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create_full']))

    def test_mismatched_invoice_pdf_is_not_delivered_or_offered_for_edo(self):
        def mismatched_pdf(crm):
            office(crm)
            original = crm.add_invoice
            crm.add_invoice = lambda deal_id, rows, **kwargs: original(
                deal_id, rows, invoice_date='20.10.2026',
                **{key: value for key, value in kwargs.items() if key != 'invoice_date'})

        def journey(person):
            yield say('990001')
            yield press('🧾 Выставить счёт')
            yield press('📋 Общий счёт по спецификации')
            yield press('✅ Выставить общий счёт')
            person.sees('дата PDF не совпала', 'повторно счёт не создавайте',
                        expected='Расхождение блокирует доставку и безопасно продолжает сценарий')
            person.not_sees('Дальше: отправить договор', expected='Несверенный файл не предлагается для ЭДО')
            documents = [event for event in person.stand.telegram.events
                         if event.get('actor') == 'bot' and event.get('kind') == 'document']
            person.check('Несверенный PDF не отправлен', documents, not documents)

        stand = self.play(journey, setup=mismatched_pdf)
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create_full']))

    def test_invoice_route_offers_required_status_inline(self):
        def needs_invoice_status(crm):
            office(crm)
            crm.deals[DEAL]['status_id'] = '1'
        def journey(person):
            yield say('990001')
            yield press('🧾 Выставить счёт')
            yield press('📋 Общий счёт по спецификации')
            person.sees('Перевести её в «Выставление счета» и выставить счёт?')
            person.sees_button('🔄 Перевести и выставить счёт')
            yield press('🔄 Перевести и выставить счёт')
            person.sees('Выставить общий счёт', expected='После перевода показан обычный preview')
            yield press('✅ Выставить общий счёт')
            person.got_document('Счёт')
        stand = self.play(journey, setup=needs_invoice_status)
        self.assertEqual(5, stand.receipt()['actions'], 'новый маршрут — 5 действий вместо 8 через отдельное меню')
        self.assertEqual('2', stand.crm.deals[DEAL]['status_id'])
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create_full']))

    def test_invoice_without_changing_status_stays_possible(self):
        # Review 07.11: the status prompt must never force a deal backwards.
        def needs_invoice_status(crm):
            office(crm)
            crm.deals[DEAL]['status_id'] = '1'
        def journey(person):
            yield say('990001')
            yield press('🧾 Выставить счёт')
            yield press('📋 Общий счёт по спецификации')
            person.sees_button('🧾 Выставить без смены статуса', expected='Можно не менять статус')
            yield press('🧾 Выставить без смены статуса')
            person.sees('Выставить общий счёт', expected='Сразу обычный предпросмотр счёта')
            yield press('✅ Выставить общий счёт')
            person.got_document('Счёт')
        stand = self.play(journey, setup=needs_invoice_status)
        self.assertEqual('1', stand.crm.deals[DEAL]['status_id'], 'статус не изменён')
        self.assertEqual([], [w for w in stand.crm.writes if w['action'] == 'move_status'])
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create_full']))

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

    def test_search_result_opens_full_invoice_preview_in_one_action(self):
        def journey(person):
            yield say('Покажи 1 сделку с Альфа Климат')
            person.sees_button('🧾 Запросить общий счёт №990002',
                               expected='У найденной сделки есть прямое продолжение к предпросмотру счёта')
            yield press('🧾 Запросить общий счёт №990002')
            person.sees('Выставить общий счёт по сделке №990002?',
                        'Плательщик:', 'Сумма:',
                        expected='Одно нажатие открыло безопасный предпросмотр общего счёта')
            person.sees_button('✅ Выставить общий счёт',
                               expected='Хозяйственная запись остаётся за отдельным подтверждением')

        stand = self.play(journey, setup=office)
        self.assertEqual(2, stand.receipt()['actions'],
                         'один поиск и одно действие от результата до предпросмотра')
        self.assertEqual([], stand.crm.writes, 'Предпросмотр не создаёт счёт')
        self.assertEqual(0, len(stand.model.prompts))

    def test_assistant_list_of_deals_gets_buttons(self):
        listing = ('Нашёл такие сделки:\n\n1. №990001 — Кондиционирование офиса\n   Этап: Заявка\n\n'
                   '2. №990002 — Вентиляция склада\n   Этап: Закупка\n\nСчёт №311 — выставлен.')
        def journey(person):
            yield say('Какие у нас сейчас интересные объекты?')
            person.sees_button('№990002 · Вентиляция склада', expected='Список сделок от ассистента — с кнопками')
            yield press('№990002 · Вентиляция склада')
            person.sees('Сделка №990002', expected='Кнопка открыла сделку без «открой карточку 990002»')
        self.play(journey, setup=office, model_rules=[('интересные объекты', listing)])

    def test_deal_found_by_the_assistant_opens_in_the_bot(self):
        answer = ('Нашёл точное соответствие:\n\n**Сделка №990002 — «Вентиляция склада»**\n- Этап: Закупка\n'
                  '- [Открыть сделку №990002 в Мегаплане](https://cclimat.megaplan.ru/deals/990002/card/)\n'
                  'Ничего в сделке не изменял.')
        def journey(person):
            yield say('Найди мне сделку вентиляции склада у Альфа Климат')
            person.sees('Сделка №990002\nСуть', expected='После ответа ассистента открыта карточка сделки в боте')
            person.sees_button('🧾 Выставить счёт', expected='Меню действий сделки доступно сразу')
            yield press('🧾 Выставить счёт')
            person.sees('Работа со счетами', expected='Работа со сделкой продолжается в боте, а не в Мегаплане')
        stand = self.play(journey, setup=office, model_rules=[('вентиляции склада', answer)])
        self.assertEqual([], stand.crm.writes)

    def test_assistant_answer_without_a_find_request_does_not_open_cards(self):
        def journey(person):
            yield say('Расскажи, что было по сделке вчера')
            person.not_sees('Сделка №990002\nСуть', expected='Карточка не открывается без просьбы найти сделку')
        self.play(journey, setup=office, model_rules=[('Расскажи', 'Вчера по сделке №990002 пришла оплата.')])

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
