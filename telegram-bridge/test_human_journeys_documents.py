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


class EconomicsWithoutRewritesJourneys(HumanJourneyCase, unittest.TestCase):
    """Owner decision 23.10: the CRM file is rewritten only when the numbers change."""

    @staticmethod
    def economics(person):
        yield press('📋 Основное')
        yield press('💰 Экономика')

    def writes(self, stand):
        return [w for w in stand.crm.writes if w['action'] == 'upsert_profitability_file']

    def test_three_presses_write_once_and_always_deliver(self):
        def journey(person):
            yield from open_deal_by_number(person)
            for attempt in range(3):
                yield from self.economics(person)
                person.sees('выручка 114 000,00 ₽', expected=f'Нажатие {attempt + 1}: цифры показаны')
                person.got_document('Рентабельность', expected=f'Нажатие {attempt + 1}: файл пришёл')
                if attempt:
                    person.sees('файл в сделке актуален', expected='Без изменений бот не переписал файл и сказал об этом')
        stand = self.play(journey, setup=office)
        self.assertEqual(1, len(self.writes(stand)))

    def test_changed_position_publishes_a_new_version(self):
        def journey(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
            person.stand.crm.deals[DEAL]['positions'][0]['qty'] = 3
            yield from self.economics(person)
            person.not_sees('файл в сделке актуален', expected='После изменения данных файл обновлён')
        stand = self.play(journey, setup=office)
        self.assertEqual(2, len(self.writes(stand)))

    def test_restart_without_changes_does_not_rewrite(self):
        def before(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
        def after(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
            person.sees('файл в сделке актуален')
        stand = self.play([before, after], setup=office)
        self.assertEqual(1, len(self.writes(stand)))

    def test_crm_failure_still_delivers_the_file(self):
        def setup(crm):
            office(crm)
            crm.failures[('deal_browser', 'upsert_profitability_file')] = 'Megaplan timeout'
        def journey(person):
            yield from open_deal_by_number(person)
            yield from self.economics(person)
            person.sees('выручка 114 000,00 ₽', 'не сохранён в сделке', expected='Цифры и честное предупреждение')
            person.got_document('Рентабельность', expected='Файл пришёл, несмотря на сбой CRM')
        self.play(journey, setup=setup)


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
