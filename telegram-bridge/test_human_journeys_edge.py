"""Human journeys, second wave: how real people actually misuse a bot.

Double taps on old buttons, typing a confirmation instead of pressing it,
colloquial phrasing, a deal without a payer or invoices, an unreachable CRM.
Each journey asserts both the visible answer and the absence of unintended writes.
"""
import unittest

from human_qa_harness import HumanJourneyCase, press, press_old, say, send_voice
from test_human_journeys import DEAL, office, open_deal_by_number


def writes(stand, action=None):
    return [w for w in stand.crm.writes if action is None or w['action'] == action]


class DealReadingVariants(HumanJourneyCase, unittest.TestCase):
    def test_status_question_in_plain_words(self):
        def journey(person):
            yield say('Какой статус у сделки 990002?')
            person.sees('Сделка №990002', 'Закупка', expected='Бот назвал статус сделки')
        self.play(journey, setup=office)

    def test_who_is_executor(self):
        def journey(person):
            yield say('Кто исполнитель по сделке 990001?')
            person.sees('Сергей Деревянко', expected='Бот назвал исполнителя сделки')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(stand.model.prompts), 'Чтение карточки не должно уходить в ИИ')

    def test_unknown_deal_number(self):
        def journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('🔢 Найти по номеру')
            yield say('99001')
            person.sees('99001', expected='Бот повторил номер, по которому ничего не нашёл')
            person.not_sees('Traceback', 'KeyError', expected='Человек не видит технический мусор')
            person.check('После ошибки можно сразу ввести другой номер',
                         person.visible_buttons(), bool(person.visible_buttons()))
            yield say('990001')
            person.sees('Сделка №990001', expected='Повторный ввод номера открыл сделку')
        self.play(journey, setup=office)

    def test_search_by_address(self):
        def journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('📍 Найти по адресу')
            yield say('Химки')
            person.sees('№990002', expected='Найдена сделка по адресу')
            person.not_sees('№990001', expected='Чужие сделки не попали в выдачу')
        self.play(journey, setup=office)

    def test_find_deals_of_client_by_phrase(self):
        def journey(person):
            yield say('Найди сделки клиента Иванов')
            person.sees('№990003', expected='Бот нашёл сделку клиента по фразе')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(stand.model.prompts), 'Поиск сделки по клиенту не должен уходить в ИИ')

    def test_current_deal_button(self):
        def journey(person):
            yield from open_deal_by_number(person, '990002')
            yield press('⬅️ К списку сделок')
            yield press('⭐ Текущая сделка')
            person.sees('Сделка №990002', expected='«Текущая сделка» вернула последнюю открытую')
        self.play(journey, setup=office)


    def test_free_phrase_finds_deal_by_object_and_city(self):
        def journey(person):
            yield say('Найди сделку по складу в Химках')
            person.sees('№990002', expected='Одна фраза нашла сделку по объекту и городу, падежи не мешают')
            person.not_sees('№990001', '№990003', expected='Чужие сделки не попали в выдачу')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(stand.model.prompts), 'Поиск сделки фразой не должен уходить в ИИ')

    def test_free_phrase_without_matches_goes_the_usual_way(self):
        def journey(person):
            yield say('Найди сделку по бассейну в Сочи')
            person.not_sees('Подходящих сделок не найдено', expected='Неуверенный поиск не перехватил разговор')
        stand = self.play(journey, setup=office, model_rules=[('', 'Сделок по бассейну в Сочи я не нашёл. Уточните клиента?')])
        self.assertEqual(1, len(stand.model.prompts))

    def test_number_in_a_description_is_not_a_deal_number(self):
        # QA 27.10 (owner, voice): «кабинет 103» opened deal №103 and started an invoice there.
        def setup(crm):
            office(crm)
            crm.add_deal('103', '502', 'Старая сделка', positions=(('Работа', 1, 1000),))
        def journey(person):
            yield say('990001')
            yield say('Найди сделку Альфа кондиционирование офиса кабинет 103 и аннулируй счёт и выстави новый')
            person.not_sees('Сделка №103', expected='Число из описания не принято за номер сделки')
            person.sees_button('№990001 · Кондиционирование офиса на Тверской', expected='Показаны варианты сделок кнопками')
            person.sees('Аннулировать счёт бот пока не умеет', expected='Честно сказано, чего бот не умеет')
            person.not_sees('Выставить общий счёт', expected='Счёт не начат ни по какой сделке до выбора')
            yield press('№990001 · Кондиционирование офиса на Тверской')
            person.sees_button('🧾 Выставить счёт', expected='Из выбранной сделки — меню действий')
        stand = self.play(journey, setup=setup)
        self.assertEqual([], stand.crm.writes)

class UnsupportedInputJourneys(HumanJourneyCase, unittest.TestCase):
    def test_voice_message_gets_an_honest_answer(self):
        def journey(person):
            yield send_voice()
            person.sees('Голосовые сообщения', 'не распознаёт', 'текстом',
                        expected='На голосовое бот честно ответил, что не понял, и что делать')
            person.sees_button('🤝 Сделки')
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)


class PayerEdgeCases(HumanJourneyCase, unittest.TestCase):
    def test_unknown_payer_name_shows_choices(self):
        def journey(person):
            yield say('Поменяй плательщика в сделке 990001 на Ромашка')
            person.sees('Ромашка', 'Текущий плательщик: ООО «Альфа Климат»',
                        expected='Бот сказал, что такого плательщика нет, и показал текущего')
            person.sees_button('ООО «Альфа Сервис» · ИНН 7701000002')
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)

    def test_double_tap_on_confirmation_writes_once(self):
        def journey(person):
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
            yield press('✅ Сменить плательщика')
            person.sees('плательщик изменён')
            yield press_old('✅ Сменить плательщика')
            person.not_sees('плательщик изменён', expected='Повторное нажатие ничего не повторило')
        stand = self.play(journey, setup=office)
        self.assertEqual(1, len([w for w in stand.crm.writes if w['script'] == 'payer_manager']))

    def test_typed_confirmation_is_not_a_write(self):
        def journey(person):
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
            yield say('✅ Сменить плательщика')
            person.sees('кнопку', expected='Бот попросил нажать кнопку под предпросмотром')
        stand = self.play(journey, setup=office)
        self.assertEqual('7101', stand.crm.deals[DEAL]['payer_id'])

    def test_crm_failure_is_reported_honestly(self):
        def setup(crm):
            office(crm)
            crm.failures[('payer_manager', 'apply')] = 'Megaplan timeout'
        def journey(person):
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
            yield press('✅ Сменить плательщика')
            person.sees('не изменён', expected='Бот честно сказал, что плательщик не изменён')
            person.not_sees('плательщик изменён на', expected='Нет ложного успеха')
        self.play(journey, setup=setup)

    def test_change_executor(self):
        def journey(person):
            yield say('Назначь исполнителем сделки 990001 Смирнова')
            person.sees_button('Сотрудник ID 1000011 — Алексей Смирнов')
            yield press('Сотрудник ID 1000011 — Алексей Смирнов')
            person.sees('Текущий исполнитель: Сергей Деревянко', 'Алексей Смирнов')
            yield press('✅ Назначить исполнителя')
            person.sees('Алексей Смирнов', expected='Исполнитель изменён')
        stand = self.play(journey, setup=office)
        self.assertEqual(['Алексей Смирнов'], stand.crm.deals[DEAL]['executors'])


class InvoiceEdgeCases(HumanJourneyCase, unittest.TestCase):
    def test_issue_invoice_by_phrase_to_the_end(self):
        def journey(person):
            yield say('Выстави счёт по сделке 990001')
            person.sees_button('📋 Общий счёт по спецификации')
            yield press('📋 Общий счёт по спецификации')
            yield press('✅ Выставить общий счёт')
            person.sees('выставлен')
            person.got_document('Счёт')
        stand = self.play(journey, setup=office)
        self.assertEqual(1, len(writes(stand, 'create_full')))

    def test_double_tap_on_invoice_creates_one_invoice(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('📋 Общий счёт по спецификации')
            yield press('✅ Выставить общий счёт')
            yield press_old('✅ Выставить общий счёт')
        stand = self.play(journey, setup=office)
        self.assertEqual(1, len(writes(stand, 'create_full')), 'Двойное нажатие выставило два счёта')

    def test_deal_without_invoices(self):
        def journey(person):
            yield say('Пришли счёт по сделке 990002')
            person.sees('990002', expected='Бот сказал, что у этой сделки счетов нет')
            person.not_sees('internal error', 'Traceback')
        self.play(journey, setup=office)

    def test_full_invoice_without_payer_explains_next_step(self):
        def setup(crm):
            office(crm)
            crm.deals['990003']['payer_id'] = None
        def journey(person):
            yield say('Выстави счёт по сделке 990003')
            yield press('📋 Общий счёт по спецификации')
            person.sees('плательщик', expected='Бот объяснил, что не выбран плательщик')
            person.sees('плательщика', expected='Бот подсказал, как добавить плательщика')
        stand = self.play(journey, setup=setup)
        self.assertEqual([], stand.crm.writes)

    def test_stage_invoice_without_contract(self):
        def journey(person):
            yield say('Выстави счёт по сделке 990003')
            yield press('6.4.1')
            person.sees('договор', expected='Бот объяснил, что нет подписанного договора')
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)

    def test_changed_deal_after_preview_is_not_invoiced_silently(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('📋 Общий счёт по спецификации')
            person.stand.crm.deals[DEAL]['positions'][0]['qty'] = 3
            yield press('✅ Выставить общий счёт')
            person.sees('изменены', expected='Бот не выставил счёт по устаревшему просмотру')
        stand = self.play(journey, setup=office)
        self.assertEqual([], writes(stand, 'create_full'))

    def test_crm_unreachable_when_issuing(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('📋 Общий счёт по спецификации')
            person.stand.crm.reachable = False
            yield press('✅ Выставить общий счёт')
            person.sees('не', expected='Бот сообщил, что счёт не выставлен')
            person.not_sees('выставлен:', expected='Нет ложного успеха')
        stand = self.play(journey, setup=office)
        self.assertEqual([], writes(stand, 'create_full'))


class DealCreationVariants(HumanJourneyCase, unittest.TestCase):
    def test_create_deal_for_unknown_client(self):
        def journey(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            yield say('Кондиционер на дачу')
            yield say('Кузнецова Мария')
            person.sees('не найдено', expected='Бот сказал, что такого клиента нет')
            person.sees_button('Новый клиент — физическое лицо')
            yield press('Новый клиент — физическое лицо')
            person.sees('спецификацию')
        self.play(journey, setup=office)

    def test_double_tap_on_create_makes_one_deal(self):
        block = ('CREATE_MEGAPLAN_DEAL_BEGIN\n{"client_name": "ООО «Альфа Климат»", "description": "Монтаж",'
                 ' "items": [{"name": "Монтаж сплит-системы", "qty": 1, "unit_price": 14000}]}\nCREATE_MEGAPLAN_DEAL_END')
        def journey(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            yield say('Монтаж')
            yield say('Альфа')
            yield press('Клиент ID 501 — ООО «Альфа Климат»')
            yield say('Монтаж сплит-системы 1 шт 14000')
            if 'НДС 22%' in person.visible_buttons():
                yield press('НДС 22%')
            yield press('✅ Создать подтверждённую сделку')
            person.sees('Сделка создана')
            yield press_old('✅ Создать подтверждённую сделку')
        stand = self.play(journey, setup=office, model_rules=[('Монтаж сплит-системы 1 шт', block)])
        self.assertEqual(1, len([w for w in stand.crm.writes if w['script'] == 'megaplan_api']))

    def test_created_deal_becomes_current(self):
        block = ('CREATE_MEGAPLAN_DEAL_BEGIN\n{"client_name": "ООО «Альфа Климат»", "description": "Монтаж",'
                 ' "items": [{"name": "Монтаж сплит-системы", "qty": 1, "unit_price": 14000}]}\nCREATE_MEGAPLAN_DEAL_END')
        def journey(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            yield say('Монтаж')
            yield say('Альфа')
            yield press('Клиент ID 501 — ООО «Альфа Климат»')
            yield say('Монтаж сплит-системы 1 шт 14000')
            if 'НДС 22%' in person.visible_buttons():
                yield press('НДС 22%')
            yield press('✅ Создать подтверждённую сделку')
            yield press('🤝 Сделки')
            yield press('⭐ Текущая сделка')
            person.sees('Сделка №990101', 'Монтаж', expected='Новая сделка открывается как текущая')
        self.play(journey, setup=office, model_rules=[('Монтаж сплит-системы 1 шт', block)])


    def test_client_in_the_title_is_offered_without_asking(self):
        def journey(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            yield say('Монтаж для ООО Альфа Климат')
            person.sees('В названии указан клиент «ООО Альфа Климат»', expected='Бот узнал клиента в названии (И-11)')
            person.not_sees('Укажите клиента', expected='Второй раз клиента не спрашивают')
            person.sees_button('Клиент ID 501 — ООО «Альфа Климат»', expected='Предложена найденная карточка для подтверждения')
            person.sees_button('🔍 Другой клиент', expected='Можно выбрать другого клиента')
            yield press('Клиент ID 501 — ООО «Альфа Климат»')
            person.sees('спецификацию', expected='Дальше — обычные позиции')
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)
        self.assertEqual(0, len(stand.model.prompts))
        self.assertEqual(4, stand.receipt()['actions'], 'до позиций — 4 действия вместо 5')

    def test_title_without_legal_form_still_asks_for_client(self):
        def journey(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            yield say('Кондиционер на дачу')
            person.sees('Укажите клиента')
        self.play(journey, setup=office)

if __name__ == '__main__':
    unittest.main()
