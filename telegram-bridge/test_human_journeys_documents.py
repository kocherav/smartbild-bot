"""Human journeys, third wave: contract, proposal, navigation and help."""
import unittest

from human_qa_harness import HumanJourneyCase, press, say
from test_human_journeys import DEAL, office, open_deal_by_number


def no_contract(crm):
    office(crm)
    crm.deals[DEAL]['contract'] = None


def to_contract_menu(person):
    yield from open_deal_by_number(person)
    yield press('📄 Документы сделки')
    yield press('📑 Работа с договором')
    person.sees_button('👁 Проверить данные договора')


class ContractJourneys(HumanJourneyCase, unittest.TestCase):
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
            yield press('✅ Сформировать договор')
            person.got_document('.docx', expected='Пришёл Word договора')
            person.got_document('.pdf', expected='Пришёл подписанный PDF')
            yield press('✅ Загрузить договоры в сделку')
            person.sees('загружены', expected='Договоры загружены в сделку')
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('6.4.1')
            yield press('✅ Выставить счёт')
            person.sees('выставлен', expected='После договора счёт по этапу выставляется')
        stand = self.play(journey, setup=no_contract)
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'upload_contracts']))
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create']))

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


class EconomicsJourneys(HumanJourneyCase, unittest.TestCase):
    def test_deal_economics_button(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📋 Основное')
            yield press('💰 Экономика')
            person.sees('выручка 114 000,00 ₽', 'себестоимость 72 000,00 ₽', 'прибыль 42 000,00 ₽', '36,8%',
                        expected='Экономика сделки в понятном формате')
            person.got_document('Рентабельность')
        self.play(journey, setup=office)


class ProposalJourneys(HumanJourneyCase, unittest.TestCase):
    def test_proposal_by_phrase(self):
        def journey(person):
            yield say('Сделай КП по сделке 990001')
            person.sees('Кому адресовать', expected='Бот спросил адресата КП')
            yield say('Алексей')
            person.got_document('КП', expected='Пришёл PDF КП')
            person.sees('2 позиций', '114 000,00', expected='Подпись КП с количеством и суммой')
        stand = self.play(journey, setup=office)
        self.assertEqual(0, len(stand.model.prompts), 'КП по сделке не должно уходить в ИИ')

    def test_proposal_from_deal_card(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield press('📋 Основное')
            yield press('📄 КП по сделке')
            yield say('Уважаемая Татьяна,')
            person.got_document('КП')
        self.play(journey, setup=office)


class NavigationJourneys(HumanJourneyCase, unittest.TestCase):
    def test_leaving_a_payer_choice_for_the_menu_forgets_it(self):
        def journey(person):
            yield say('Нужно сменить плательщика')
            yield say('990001')
            yield press('🤝 Сделки')
            person.sees_button('🔎 Найти сделку', expected='Главное меню доступно посреди сценария')
            yield say('Альфа Сервис')
            person.not_sees('Новый плательщик', expected='Брошенный выбор плательщика не продолжился сам')
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
