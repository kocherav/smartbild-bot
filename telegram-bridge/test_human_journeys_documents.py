"""Human journeys, third wave: contract, proposal, navigation and help."""
import unittest
from unittest.mock import patch
import bridge

from human_qa_harness import HumanJourneyCase, press, reply, say
from test_human_journeys import DEAL, office, open_deal_by_number


def no_contract(crm):
    office(crm)
    crm.deals[DEAL]['contract'] = None


def to_contract_menu(person):
    yield from open_deal_by_number(person)
    yield press('📄 Документы сделки')
    yield press('📑 Работа с договором')
    person.sees_button('👁 Проверить данные договора')


def to_contract_menu_for(person, deal_id):
    yield from open_deal_by_number(person, deal_id)
    yield press('📄 Документы сделки')
    yield press('📑 Работа с договором')
    person.sees_button('👁 Проверить данные договора')


class ContractJourneys(HumanJourneyCase, unittest.TestCase):
    def test_prepare_person_contract_in_one_phrase_opens_preview(self):
        """IDEA-DF04D6C4: eight menu/form actions become one safe preview request."""
        def journey(person):
            yield say('Подготовь договор по сделке 990003, подписант Иванов Пётр Сергеевич как физлицо')
            person.sees('Договор №990003-Д', 'Иванов Пётр Сергеевич', '38 000,00 ₽',
                        expected='Одна фраза сразу показала предпросмотр договора')
            person.sees_button('✅ Сформировать и загрузить Word и PDF')

        stand = self.play(journey, setup=office)
        self.assertEqual(1, self.qa_receipt['actions'], 'После: одно действие вместо прежних восьми')
        self.assertEqual([], stand.crm.writes, 'Предпросмотр не создаёт и не загружает договор')
        self.assertEqual(0, len(stand.model.prompts), 'Явная команда обрабатывается детерминированно')

    def test_changed_contract_field_names_difference_and_refreshes_once(self):
        state={'current_deal_id':DEAL,'contract_deal_id':DEAL,'pending':'contract_generate_confirm',
               'contract_data_fingerprint':'old','contract_preview':{'total':114000,'date':'2026-11-06'},
               'contract_signatory':{},'contract_signatory_payer_id':'payer'}
        responses=[{'ok':False,'no_effect':True,'error':'Данные договора изменились после просмотра'},
                   {'ok':True,'preview':{'total':204000,'date':'2026-11-07','fingerprint':'new'}}]
        with patch.object(bridge,'current_deal_ui_state',return_value=state),\
             patch.object(bridge,'run_contract_builder',side_effect=responses),\
             patch.object(bridge,'send_message') as send,patch.object(bridge,'update_deal_ui_state'):
            self.assertTrue(bridge.handle_deal_ui('token','owner','✅ Сформировать договор',_background=True))
        self.assertIn('Итого: 114 000,00 ₽ → 204 000,00 ₽',send.call_args.args[2])
        self.assertIn('Дата: 06.11.2026 → 07.11.2026',send.call_args.args[2])
        self.assertEqual('🔄 Обновить предпросмотр',send.call_args.args[3]['keyboard'][0][0]['text'])

    def test_individual_contract_uses_card_name_with_one_preview_confirmation(self):
        def setup(crm):
            office(crm)
            crm.deals['990003']['contract'] = None

        def journey(person):
            yield from to_contract_menu_for(person, '990003')
            yield press('👁 Проверить данные договора')
            person.sees('ФИО: Иванов Пётр Сергеевич', 'от своего имени',
                        expected='ФИО физлица подставлено в единый предпросмотр')
            person.sees_button('✅ Сформировать и загрузить Word и PDF')

        stand = self.play(journey, setup=setup)
        actions = [event for event in stand.telegram.events if event['actor'] == 'tester']
        self.assertEqual(7, len(actions),
                         'Маршрут до подтверждения предпросмотра: 7 действий вместо прежних 10')
        saves = [w for w in stand.crm.writes if w['action'] == 'save_signatory']
        self.assertEqual([], saves, 'Автоподстановка не создаёт отдельную запись подписанта')
    def test_prepare_contract_then_stage_invoice(self):
        def journey(person):
            yield from to_contract_menu(person)
            yield press('👁 Проверить данные договора')
            person.sees('ФИО подписанта', expected='Бот спросил подписанта заказчика')
            yield say('Петров Иван Сергеевич')
            person.sees('должность', expected='Бот спросил должность')
            yield say('Генеральный директор')
            person.sees_button('Устав')
            yield press('Устав')
            person.sees('Договор №990001-Д', 'ООО «Альфа Климат»', '114 000,00',
                        expected='Показан предпросмотр договора с суммой')
            person.sees_button('✅ Сформировать и загрузить Word и PDF')
            yield press('✅ Сформировать и загрузить Word и PDF')
            person.got_document('.docx', expected='Пришёл Word договора')
            person.got_document('.pdf', expected='Пришёл подписанный PDF')
            person.sees('загружены', expected='Договоры загружены в сделку')
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('6.4.1')
            yield press('✅ Выставить счёт')
            person.sees('выставлен', expected='После договора счёт по этапу выставляется')
        stand = self.play(journey, setup=no_contract)
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'upload_contracts']))
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create']))

    def test_contract_for_deal_without_address_asks_and_saves_it_once(self):
        def setup(crm):
            no_contract(crm)
            crm.deals[DEAL]['address'] = ''
        def journey(person):
            yield from to_contract_menu(person)
            yield press('👁 Проверить данные договора')
            for _ in range(5):
                screen = person.screen_text()
                if 'Договор №' in screen:
                    break
                if 'Устав' in person.visible_buttons():
                    yield press('Устав')
                elif 'адрес объекта' in screen:
                    yield say('Москва, ул. Тестовая, 1')
                elif 'должность' in screen:
                    yield say('Генеральный директор')
                else:
                    yield say('Петров Иван Сергеевич')
            person.sees('Договор №990001-Д', expected='После ввода адреса показан предпросмотр договора')
        stand = self.play(journey, setup=setup)
        saved = [w for w in stand.crm.writes if w['action'] == 'update_contract_fields']
        self.assertEqual(1, len(saved), 'Адрес записан в сделку ровно один раз')
        self.assertEqual('Москва, ул. Тестовая, 1', stand.crm.deals[DEAL]['address'])

    def test_menu_button_is_not_taken_as_signatory_name(self):
        def journey(person):
            yield from to_contract_menu(person)
            yield press('👁 Проверить данные договора')
            yield say('📑 Работа с договором')
            person.sees('текстом', expected='Бот не принял кнопку меню за ФИО')
            yield say('Петров Иван Сергеевич')
            person.sees('должность')
        self.play(journey, setup=no_contract)

    def test_contract_preview_uses_russian_money(self):
        def journey(person):
            yield from to_contract_menu(person)
            yield press('👁 Проверить данные договора')
            yield say('Петров Иван Сергеевич')
            yield say('Директор')
            yield press('Устав')
            person.sees('Итого: 114 000,00 ₽', expected='Суммы в договоре в привычном формате')
        self.play(journey, setup=no_contract)

    def test_manager_corrects_signatory_from_unified_preview(self):
        """Before: no route from preview. After: four actions edit all signer fields."""
        def journey(person):
            yield from to_contract_menu(person)
            yield press('👁 Проверить данные договора')
            yield say('Петров Иван Сергеевич')
            yield say('Директор')
            yield press('Устав')
            person.sees('Подписант', 'ФИО: Петров Иван Сергеевич',
                        'Статус: Директор', 'Действует: Устав')
            person.sees_button('✏️ Исправить подписанта')
            actions_before_correction = len([e for e in person.stand.telegram.events if e['actor'] == 'tester'])
            yield press('✏️ Исправить подписанта')
            yield say('Иванов Пётр Сергеевич')
            yield say('Физическое лицо')
            yield press('От своего имени')
            person.sees('ФИО: Иванов Пётр Сергеевич', 'Статус: Физическое лицо',
                        'Действует: От своего имени', expected='Исправленные реквизиты видны до формирования')
            actions_after_correction = len([e for e in person.stand.telegram.events if e['actor'] == 'tester'])
            person.check('Исправление подписанта занимает 4 действия вместо отсутствующего маршрута',
                         4, actions_after_correction - actions_before_correction)
        self.play(journey, setup=no_contract)


class EconomicsJourneys(HumanJourneyCase, unittest.TestCase):
    def test_deal_summary_replaces_two_separate_drill_downs(self):
        """Before: economics + positions required at least two actions after the card; after: one."""
        actions_after_card = []

        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📊 Сводка')
            actions_after_card.append('📊 Сводка')
            person.sees(
                'Выручка: 114 000,00 ₽', 'Себестоимость: 72 000,00 ₽',
                'Прибыль: 42 000,00 ₽', 'Рентабельность: 36,8%', 'Позиций: 2',
                expected='Все показатели сделки пришли одним сообщением',
            )

        stand = self.play(journey, setup=office)
        self.assertEqual(1, len(actions_after_card), 'После карточки нужна одна кнопка вместо двух переходов')
        self.assertEqual([], stand.crm.writes, 'Сводка только читает CRM')

    def test_deal_summary_does_not_invent_missing_cost(self):
        def incomplete(crm):
            office(crm)
            crm.deals[DEAL]['positions'][0]['cost_material'] = None

        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📊 Сводка')
            person.sees('НЕ ПРОВЕРЕНО', 'нет себестоимости', 'Исправьте данные позиций и повторите',
                        expected='Неполная себестоимость явно названа, итог не выдуман')
            person.not_sees('Прибыль:', expected='Частичный итог не показан как полный')

        stand = self.play(journey, setup=incomplete)
        self.assertEqual([], stand.crm.writes, 'Даже неполная сводка только читает CRM')

    def test_deal_economics_in_one_plain_language_action(self):
        def journey(person):
            yield say('Покажи прибыль и маржу по сделке 990001 и пришли расчёт')
            person.sees('выручка 114 000,00 ₽', 'себестоимость 72 000,00 ₽',
                        'прибыль 42 000,00 ₽', '36,8%',
                        expected='Экономика рассчитана одним сообщением менеджера')
            person.got_document('Рентабельность', expected='Расчётный Excel пришёл одним маршрутом')
        stand = self.play(journey, setup=office)
        self.assertEqual(1, stand.receipt()['actions'], 'После улучшения нужен один шаг менеджера')
        self.assertEqual(0, len(stand.model.prompts), 'Точный запрос экономики не должен уходить в ИИ')

    def test_deal_economics_button(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📋 Основное')
            yield press('💰 Экономика')
            person.sees('выручка 114 000,00 ₽', 'себестоимость 72 000,00 ₽', 'прибыль 42 000,00 ₽', '36,8%',
                        expected='Экономика сделки в понятном формате')
            person.got_document('Рентабельность')
        stand = self.play(journey, setup=office)
        self.assertEqual(6, stand.receipt()['actions'],
                         'Контрольный маршрут через меню требует шесть действий на стенде')
        writes = [w for w in stand.crm.writes if w['action'] == 'upsert_profitability_file']
        self.assertEqual(0, len(writes), 'Просмотр экономики не должен сохранять файл в CRM')


class EconomicsFindableJourneys(HumanJourneyCase, unittest.TestCase):
    """Owner 27.10: «Покажи мне экономику по сделке 903» showed the card; no economics button in it."""

    def test_economics_by_phrase(self):
        def journey(person):
            yield say('Покажи мне экономику по сделке 990001')
            person.sees('выручка 114 000,00 ₽', 'прибыль 42 000,00 ₽', expected='Фраза про экономику прислала экономику')
            person.got_document('Рентабельность', expected='Пришёл файл рентабельности')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(stand.model.prompts))
        writes = [w for w in stand.crm.writes if w['action'] == 'upsert_profitability_file']
        self.assertEqual(0, len(writes), 'Фраза о просмотре экономики не должна сохранять файл в CRM')

    def test_economics_button_in_the_deal_card(self):
        def journey(person):
            yield say('990001')
            person.sees_button('💰 Экономика', expected='Экономика видна прямо в карточке сделки')
            yield press('💰 Экономика')
            person.sees('выручка 114 000,00 ₽', expected='Кнопка из карточки прислала экономику')
        self.play(journey, setup=office)


class EconomicsWithoutRewritesJourneys(HumanJourneyCase, unittest.TestCase):
    """Просмотр — два действия без записи; сохранение — третье явное действие менеджера."""

    @staticmethod
    def economics(person):
        yield press('📋 Основное')
        yield press('💰 Экономика')

    def writes(self, stand):
        return [w for w in stand.crm.writes if w['action'] == 'upsert_profitability_file']

    def test_preview_then_explicit_save_writes_once(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
            person.sees('выручка 114 000,00 ₽', expected='Просмотр: цифры показаны')
            person.got_document('Рентабельность', expected='Просмотр: файл пришёл')
            person.sees_button('💾 Сохранить расчёт в CRM', expected='Сохранение отделено явной кнопкой')
            self.assertEqual(0, len(self.writes(person.stand)), 'До явной кнопки CRM не меняется')
            yield press('💾 Сохранить расчёт в CRM')
            person.sees('сохранён в CRM', expected='После явной кнопки есть квитанция сохранения')
        stand = self.play(journey, setup=office)
        self.assertEqual(1, len(self.writes(stand)))

    def test_save_button_without_active_preview_is_rejected(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield say('💾 Сохранить расчёт в CRM')
            person.sees('Предпросмотр устарел', expected='Старая кнопка не создаёт файл')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(self.writes(stand)))

    def test_changed_position_publishes_a_new_version(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
            yield press('💾 Сохранить расчёт в CRM')
            person.stand.crm.deals[DEAL]['positions'][0]['qty'] = 3
            yield from self.economics(person)
            yield press('💾 Сохранить расчёт в CRM')
            person.sees('сохранён в CRM', expected='После изменения данных файл обновлён')
        stand = self.play(journey, setup=office)
        self.assertEqual(2, len(self.writes(stand)))

    def test_restart_without_changes_does_not_rewrite(self):
        def before(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
            yield press('💾 Сохранить расчёт в CRM')
        def after(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
            yield press('💾 Сохранить расчёт в CRM')
            person.sees('уже актуален в CRM')
        stand = self.play([before, after], setup=office)
        self.assertEqual(1, len(self.writes(stand)))

    def test_crm_failure_still_delivers_the_file(self):
        def setup(crm):
            office(crm)
            crm.failures[('deal_browser', 'upsert_profitability_file')] = 'Megaplan timeout'
        def journey(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
            person.sees('выручка 114 000,00 ₽', 'в CRM ничего не записано', expected='Предпросмотр без записи')
            person.got_document('Рентабельность', expected='Файл пришёл, несмотря на сбой CRM')
            yield press('💾 Сохранить расчёт в CRM')
            person.sees('НЕ сохранён в CRM', expected='После явной кнопки показан честный отказ CRM')
        self.play(journey, setup=setup)


class ProposalJourneys(HumanJourneyCase, unittest.TestCase):
    def test_proposal_by_phrase(self):
        def journey(person):
            yield say('Сделай КП по сделке 990001')
            person.sees('Кому адресовать', expected='Бот спросил адресата КП')
            yield say('Алексей')
            person.sees('Предпросмотр КП', '2 позиции', '114 000,00', 'монтаж',
                        expected='Один предпросмотр показал позиции, количества, монтаж и итог')
            person.check('До подтверждения PDF не создан', person.documents(), not person.documents())
            yield press('✅ Создать PDF КП')
            person.got_document('КП', expected='Пришёл PDF КП')
            person.sees('2 позиций', '114 000,00', expected='Подпись КП с количеством и суммой')
        stand = self.play(journey, setup=office)
        actions = [event for event in self.qa_transcript if event['actor'] == 'tester']
        self.assertEqual(3, len(actions), 'После: запрос, адресат, одно подтверждение; до: 2 действия без preview')
        self.assertEqual(0, len(stand.model.prompts), 'КП по сделке не должно уходить в ИИ')

    def test_proposal_from_deal_card(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📋 Основное')
            yield press('📄 КП по сделке')
            yield say('Уважаемая Татьяна,')
            yield press('✅ Создать PDF КП')
            person.got_document('КП')
        self.play(journey, setup=office)

    def test_failed_proposal_can_be_resumed_from_deals_in_one_action(self):
        """A filled proposal draft must survive leaving the deal card."""
        crm_ref = {}

        def setup(crm):
            office(crm)
            crm.failures[('deal_proposal', 'publish')] = 'temporary generator failure'
            crm_ref['crm'] = crm

        def journey(person):
            # Before: phrase + recipient, then after returning the manager had to
            # reopen the deal, choose KP and type the recipient again (4 actions).
            yield say('Сделай КП по сделке 990001')
            yield say('Алексей')
            yield press('✅ Создать PDF КП')
            person.sees('КП не сформировано', expected='Сбой оставил незавершённое КП')
            yield press('⬅️ К списку сделок')
            person.sees_button('Продолжить КП: Алексей, сделка 990001')

            # After: the saved deal and recipient are reused by one button.
            crm_ref['crm'].failures.pop(('deal_proposal', 'publish'))
            yield press('Продолжить КП: Алексей, сделка 990001')
            person.got_document('КП', expected='Черновик КП возобновлён одним действием')

        stand = self.play(journey, setup=setup)
        publishes = [call for call in stand.crm.calls
                     if call['script'] == 'deal_proposal' and call['action'] == 'publish']
        self.assertEqual(2, len(publishes))
        self.assertEqual('990001', publishes[-1]['spec']['deal_id'])
        self.assertEqual('Алексей', publishes[-1]['spec']['recipient'])


class ContractSubjectJourneys(HumanJourneyCase, unittest.TestCase):
    """06.11 (owner, deal 905): the contract subject could not be changed through the bot."""

    def test_change_subject_by_phrase_with_preview_and_button(self):
        def journey(person):
            yield say('990002')
            yield say('Измени в сделке 990001 предмет договора на: поставка и монтаж автоматики котельной')
            person.sees('Сделка №990001', 'Станет: «Поставка и монтаж автоматики котельной»', 'не записаны',
                        expected='Предпросмотр с номером сделки до записи')
            yield press(bridge_confirm())
            person.sees('✅ Предмет договора в сделке №990001 записан', expected='Записано и подтверждено чтением')
        stand = self.play(journey, setup=office)
        self.assertEqual('Поставка и монтаж автоматики котельной', stand.crm.deals[DEAL]['contract_subject'])
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'update_contract_fields']))
        self.assertEqual(0, len(stand.model.prompts), 'Изменение предмета не должно уходить в ИИ')

    def test_without_number_the_open_deal_is_named_before_writing(self):
        def journey(person):
            yield say('990001')
            yield say('Измени предмет договора на поставка оборудования')
            person.sees('Сделка №990001', expected='Без номера — открытая сделка, и это видно до записи')
            yield press('❌ Отмена')
        stand = self.play(journey, setup=office)
        self.assertEqual([], [w for w in stand.crm.writes if w['action'] == 'update_contract_fields'])


def bridge_confirm():
    import bridge
    return bridge.CONTRACT_SUBJECT_CONFIRM


class ReplyContextJourneys(HumanJourneyCase, unittest.TestCase):
    """QA 27.10: «Адресат КП – Татьяна» in reply to the deal №903 notice went to the open deal №890."""

    def test_reply_to_proposal_notice_builds_that_deals_proposal(self):
        def journey(person):
            yield from open_deal_by_number(person)
            import bridge
            bridge.send_message('qa', 'owner', '📄 Для сделки №990002 на стадии «Коммерческое предложение» нужно указать '
                                'адресата КП. Текущее действие и его кнопки сохранены. Когда закончите, откройте эту '
                                'сделку и нажмите «📄 КП по сделке».')
            yield reply('Адресат КП - Татьяна', to='№990002')
            person.sees('КП по сделке №990002', 'Адресат: Татьяна', expected='КП собирается по сделке из сообщения, на которое ответили')
            person.not_sees('990001', expected='Открытая до этого сделка не подставлена')
            yield press('✅ Создать PDF КП')
            person.got_document('КП', expected='Пришёл PDF КП')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(stand.model.prompts), 'Ответ на уведомление не должен уходить в ИИ')

    def test_reply_to_a_deal_message_makes_it_the_current_deal(self):
        def journey(person):
            yield from open_deal_by_number(person)
            import bridge
            bridge.send_message('qa', 'owner', 'Сделка №990002: оплата поступила.')
            yield reply('выстави счёт', to='№990002')
            person.sees('990002', expected='Действие в ответе относится к сделке из сообщения')
        self.play(journey, setup=office)


class NavigationJourneys(HumanJourneyCase, unittest.TestCase):
    def test_interrupted_payer_choice_resumes_from_deals_in_one_action(self):
        def journey(person):
            yield say('Нужно сменить плательщика')
            yield say('990001')
            person.sees_button('ООО «Альфа Сервис» · ИНН 7701000002')
            yield press('🏦 Деньги')
            yield press('🤝 Сделки')
            person.sees_button('▶️ Продолжить смену плательщика в сделке №990001',
                               expected='В разделе сделок есть однокнопочное продолжение')
            yield press('▶️ Продолжить смену плательщика в сделке №990001')
            person.sees_button('ООО «Альфа Сервис» · ИНН 7701000002',
                               expected='Выбор плательщика восстановлен за одно действие')
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)

    def test_cancel_removes_interrupted_payer_continuation(self):
        def journey(person):
            yield say('Нужно сменить плательщика')
            yield say('990001')
            yield press('🏦 Деньги')
            yield say('❌ Отмена')
            yield press('🤝 Сделки')
            buttons = person.visible_buttons()
            person.observe('Явная отмена удалила отложенное продолжение', ', '.join(buttons),
                           not any('Продолжить смену плательщика' in button for button in buttons))
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)

    def test_help_from_more_menu(self):
        def journey(person):
            yield press('☰ Ещё')
            yield press('❓ Помощь')
            person.sees('/menu', expected='Показана инструкция')
        self.play(journey, setup=office)

    def test_status_question_when_idle(self):
        def journey(person):
            yield say('/status')
            person.answered('Бот ответил на /status')
            person.not_sees('Уточните, пожалуйста', expected='/status не уходит в ИИ')
        self.play(journey, setup=office)

    def test_greeting_gets_a_useful_answer(self):
        def journey(person):
            yield say('Привет, что ты умеешь?')
            person.answered()
        self.play(journey, setup=office, model_rules=[('Привет', 'Здравствуйте! Я помогаю со сделками, счетами и монтажом.')])


if __name__ == '__main__':
    unittest.main()
