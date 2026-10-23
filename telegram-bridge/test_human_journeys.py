"""Human journeys: a person operates the real bot through Telegram controls.

Each case is a conversation.  The tester types what a manager would type and
presses only buttons that are actually on the screen; then the result is checked
the way a person checks it (what the bot said, which file arrived) and in the
CRM double (what was actually written).  Registry: docs/architecture/HUMAN_JOURNEYS.json.
"""
import unittest

from human_qa_harness import HumanJourneyCase, press, say


ALPHA = '501'
DEAL = '990001'


def office(crm):
    """A small, plausible CRM: two clients, three deals, invoices and staff."""
    crm.add_client(ALPHA, 'ООО «Альфа Климат»', payers=[
        ('7101', 'ООО «Альфа Климат»', '7701000001'),
        ('7102', 'ООО «Альфа Сервис»', '7701000002'),
    ])
    crm.add_client('502', 'Иванов Пётр Сергеевич', kind='human', payers=[('7201', 'Иванов Пётр Сергеевич', '')])
    crm.add_deal(DEAL, ALPHA, 'Кондиционирование офиса на Тверской', status_id='1',
                 address='Москва, Тверская ул., 7', executors=['Сергей Деревянко'], payer_id='7101',
                 positions=[('Сплит-система Haier AS25', 2, 45000, 30000, None),
                            ('Монтаж сплит-системы', 2, 12000, None, 6000)],
                 contract='Договор 990001-Д.pdf')
    crm.add_deal('990002', ALPHA, 'Вентиляция склада', status_id='3', address='Химки, Заводская 3',
                 payer_id='7102', positions=[('Приточная установка', 1, 150000, 110000, None)])
    crm.add_deal('990003', '502', 'Кондиционер в квартиру', status_id='1', address='Москва, Ленина 1',
                 payer_id='7201', positions=[('Сплит-система Daichi', 1, 38000, 25000, None)])
    crm.add_invoice(DEAL, [{'name': 'Сплит-система Haier AS25', 'qty': 2, 'price': 45000},
                           {'name': 'Монтаж сплит-системы', 'qty': 2, 'price': 12000}], number='311')
    crm.add_employee('1000010', 'Сергей Деревянко')
    crm.add_employee('1000011', 'Алексей Смирнов')


def open_deal_by_number(person, deal_id=DEAL):
    yield press('🤝 Сделки')
    person.sees_button('🔎 Найти сделку')
    yield press('🔎 Найти сделку')
    person.sees_button('🔢 Найти по номеру')
    yield press('🔢 Найти по номеру')
    person.answered('Бот спросил номер сделки')
    yield say(deal_id)
    person.sees(f'Сделка №{deal_id}', expected=f'Открылась карточка сделки №{deal_id}')


class DealInformationJourneys(HumanJourneyCase, unittest.TestCase):
    def test_find_deal_by_number_and_read_its_card(self):
        def journey(person):
            yield from open_deal_by_number(person)
            person.sees('ООО «Альфa Климат»'.replace('a', 'а'), 'Тверская', '114 000',
                        expected='Карточка показывает клиента, адрес и сумму сделки')
            yield press('📋 Основное')
            yield press('📄 Позиции сделки')
            person.sees('Сплит-система Haier AS25', 'Монтаж сплит-системы', '114 000,00',
                        expected='По кнопке «Позиции сделки» бот перечислил позиции и итог')
            person.got_document('Позиции сделки 990001', expected='Пришёл Excel с позициями под понятным именем')
        self.play(journey, setup=office)

    def test_ask_about_deal_in_plain_words(self):
        def journey(person):
            yield say('Покажи сделку 990001')
            person.sees('Сделка №990001', 'Тверская', expected='Сделка открыта обычной фразой')
            yield say('Сколько себестоимость по сделке 990001 и совпадает ли сумма?')
            person.sees('Совпадает: да', 'Общая себестоимость позиций: 72 000,00',
                        expected='Бот посчитал сумму и себестоимость по свежим позициям')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(stand.model.prompts), 'Чтение сделки не должно уходить в ИИ')

    def test_find_deal_by_client_name(self):
        def journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('🔎 Найти по клиенту')
            yield say('Альфа')
            person.sees('№990001', '№990002', expected='Найдены обе сделки клиента Альфа')
            person.sees_button('№990002 · Вентиляция склада')
            yield press('№990002 · Вентиляция склада')
            person.sees('Сделка №990002', 'Химки', expected='Выбранная из списка сделка открылась')
        self.play(journey, setup=office)

    def test_recent_deals(self):
        def journey(person):
            yield press('🤝 Сделки')
            yield press('🕘 Последние сделки')
            yield press('🕘 5')
            person.sees('№990003', '№990002', '№990001', expected='Показан список последних сделок')
        self.play(journey, setup=office)

    def test_check_payment_of_deal(self):
        def journey(person):
            yield say('Оплачена ли сделка 990001?')
            person.sees('Сделка №990001', 'Остаток по выставленным счетам', expected='Бот ответил по оплате сделки')
        self.play(journey, setup=office)


class PayerJourneys(HumanJourneyCase, unittest.TestCase):
    def test_change_payer_in_one_phrase(self):
        def journey(person):
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
            person.sees('ООО «Альфа Климат»', 'ООО «Альфа Сервис»', 'не записаны',
                        expected='Бот показал текущего и нового плательщика до записи')
            person.sees_button('✅ Сменить плательщика')
            yield press('✅ Сменить плательщика')
            person.sees('плательщик изменён', 'Альфа Сервис', expected='Бот подтвердил смену обратным чтением')
        stand = self.play(journey, setup=office)
        self.assertEqual('7102', stand.crm.deals[DEAL]['payer_id'])
        self.assertEqual(1, len([w for w in stand.crm.writes if w['script'] == 'payer_manager']))

    def test_change_payer_step_by_step(self):
        def journey(person):
            yield say('Нужно сменить плательщика')
            person.sees('сделк', expected='Бот спросил, в какой сделке')
            yield say('990001')
            person.sees_button('ООО «Альфа Сервис» · ИНН 7701000002')
            yield press('ООО «Альфа Сервис» · ИНН 7701000002')
            yield press('✅ Сменить плательщика')
            person.sees('плательщик изменён')
        stand = self.play(journey, setup=office)
        self.assertEqual('7102', stand.crm.deals[DEAL]['payer_id'])

    def test_cancel_payer_change_writes_nothing(self):
        def journey(person):
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
            yield press('❌ Отмена')
            person.sees('отменено', expected='Бот подтвердил отмену')
        stand = self.play(journey, setup=office)
        self.assertEqual('7101', stand.crm.deals[DEAL]['payer_id'])
        self.assertEqual([], stand.crm.writes)

    def test_payer_from_open_deal_card(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield say('Смени плательщика на Альфа Сервис')
            person.sees('Альфа Сервис', 'не записаны',
                        expected='Плательщик меняется в открытой сделке без повторного номера')
            yield press('✅ Сменить плательщика')
            person.sees('плательщик изменён')
        stand = self.play(journey, setup=office)
        self.assertEqual('7102', stand.crm.deals[DEAL]['payer_id'])


class InvoiceJourneys(HumanJourneyCase, unittest.TestCase):
    def test_issue_full_invoice_from_deal_menu(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('📋 Общий счёт по спецификации')
            person.sees('ООО «Альфа Климат»', '114 000', expected='Перед выставлением показаны плательщик и сумма')
            yield press('✅ Выставить общий счёт')
            person.sees('выставлен', expected='Бот сообщил номер нового счёта')
            person.got_document('Счёт', expected='Пришёл PDF выставленного счёта')
        stand = self.play(journey, setup=office)
        created = [w for w in stand.crm.writes if w['action'] == 'create_full']
        self.assertEqual(1, len(created))

    def test_issue_stage_invoice_by_contract_clause(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('6.4.1')
            person.sees('п.6.4.1', expected='Показана строка будущего счёта по пункту договора')
            yield press('✅ Выставить счёт')
            person.sees('выставлен', expected='Счёт по этапу выставлен')
            person.got_document('Счёт')
        stand = self.play(journey, setup=office)
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create']))

    def test_get_existing_invoice(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📄 Документы сделки')
            yield press('📥 Получить счёт')
            person.got_document('311', expected='Пришёл последний счёт сделки')
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)

    def test_download_one_of_the_invoices(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('📚 Скачать счёт')
            person.sees_button('📥 №311 · 114000 ₽ · общий')
            yield press('📥 №311 · 114000 ₽ · общий')
            person.got_document('311')
        self.play(journey, setup=office)

    def test_invoice_command(self):
        def journey(person):
            yield say('/сделка 990001')
            person.got_document('311', expected='Команда /сделка прислала последний счёт')
        self.play(journey, setup=office)

    def test_issue_invoice_in_plain_words(self):
        def journey(person):
            yield say('Выстави счёт по сделке 990001')
            person.answered()
            person.not_sees('Уточните, пожалуйста', expected='Бот не отвечает отпиской на ясное поручение')
        self.play(journey, setup=office)


class DealStatusJourneys(HumanJourneyCase, unittest.TestCase):
    def test_move_deal_to_next_status(self):
        def journey(person):
            yield from open_deal_by_number(person, '990003')
            yield press('📋 Основное')
            yield press('🔄 Изменить статус')
            person.sees_button('➡️ Закупка')
            yield press('➡️ Закупка')
            yield press('✅ Подтвердить')
            person.sees('Закупка', expected='Бот подтвердил новый статус')
        stand = self.play(journey, setup=office)
        self.assertEqual('3', stand.crm.deals['990003']['status_id'])


class DealCreationJourneys(HumanJourneyCase, unittest.TestCase):
    def test_create_deal_with_wizard_and_text_specification(self):
        spec_block = ('Черновик готов.\nCREATE_MEGAPLAN_DEAL_BEGIN\n'
                      '{"client_name": "ООО «Альфа Климат»", "description": "Кондиционеры для переговорной", '
                      '"items": [{"name": "Сплит-система Haier AS35", "qty": 2, "unit_price": 52000, "cost_material": 36000},'
                      ' {"name": "Монтаж сплит-системы", "qty": 2, "unit_price": 14000, "cost_work": 7000}]}\n'
                      'CREATE_MEGAPLAN_DEAL_END')

        def journey(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            person.sees('Как назвать', expected='Бот спросил название сделки')
            yield say('Кондиционеры для переговорной')
            person.sees('клиента', expected='Бот спросил клиента')
            yield say('Альфа')
            person.sees_button('Клиент ID 501 — ООО «Альфа Климат»')
            yield press('Клиент ID 501 — ООО «Альфа Климат»')
            person.sees('спецификацию', expected='Бот попросил спецификацию')
            yield say('Сплит-система Haier AS35 — 2 шт по 52000, закупка 36000; монтаж сплит-системы — 2 по 14000, себестоимость 7000')
            if 'НДС 22%' in person.visible_buttons():
                yield press('НДС 22%')
            person.sees('Проверьте новую сделку', 'Haier AS35', '2 × 52 000,00', '132 000,00',
                        expected='Перед созданием показан полный черновик с итогом')
            yield press('✅ Создать подтверждённую сделку')
            person.sees('Сделка создана', expected='Бот сообщил о создании сделки')
        stand = self.play(journey, setup=office, model_rules=[('Сплит-система Haier AS35', spec_block)])
        created = [w for w in stand.crm.writes if w['script'] == 'megaplan_api']
        self.assertEqual(1, len(created))
        self.assertEqual('501', str(created[0]['spec'].get('client_id')))
        self.assertIn(created[0]['spec'].get('tax_mode'), ('none', '22', '5'))
        self.assertEqual(132000, sum(i['qty'] * i['unit_price'] for i in created[0]['spec']['items']))

    def test_cancel_deal_creation_creates_nothing(self):
        def journey(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            yield say('Тестовая сделка')
            yield press('❌ Отмена')
            person.answered('Бот отреагировал на отмену')
            yield press('🤝 Сделки')
            person.sees_button('🔎 Найти сделку', expected='После отмены человек снова в меню сделок')
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)


if __name__ == '__main__':
    unittest.main()
