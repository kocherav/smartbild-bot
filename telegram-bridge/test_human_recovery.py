"""Human journeys across a bot restart: what a person sees and what is written.

A list passed to ``play`` is one conversation with a restart between its parts;
``crash_after_write`` kills the process right after the CRM accepted a write.
"""
import unittest

from human_qa_harness import HumanJourneyCase, press, press_old, say
from test_human_journeys import DEAL, office, open_deal_by_number


def open_invoice_preview(person):
    yield from open_deal_by_number(person)
    yield press('📄 Документы сделки')
    yield press('🧾 Работа со счетами')
    yield press('📋 Общий счёт по спецификации')


def writes(stand, action):
    return [w for w in stand.crm.writes if w['action'] == action]


class RestartJourneys(HumanJourneyCase, unittest.TestCase):
    def test_preview_survives_restart_and_is_written_once(self):
        def before(person):
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
        def after(person):
            yield press_old('✅ Сменить плательщика')
            person.sees('плательщик изменён', expected='Подтверждение из предпросмотра работает после перезапуска')
        stand = self.play([before, after], setup=office)
        self.assertEqual('7102', stand.crm.deals[DEAL]['payer_id'])
        self.assertEqual(1, len(writes(stand, 'link')))

    def test_current_deal_and_creation_wizard_survive_restart(self):
        def before(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            yield say('Монтаж в офис')
            yield say('Альфа')
        def after(person):
            yield press_old('Клиент ID 501 — ООО «Альфа Климат»')
            person.sees('спецификацию', expected='Мастер создания сделки продолжился после перезапуска')
        self.play([before, after], setup=office)

    def test_crash_after_payer_write_is_settled_by_readback(self):
        def setup(crm):
            office(crm)
            crm.crash_after_write.add(('payer_manager', 'link'))
        def before(person):
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
            yield press('✅ Сменить плательщика')
        def after(person):
            person.sees('Проверил Мегаплан', 'Альфа Сервис', 'Повторять не нужно',
                        expected='После перезапуска бот сам сверил прерванную смену плательщика')
            yield say('/status')
            person.sees('нет выполняющихся записей', expected='Сверенная операция больше не блокирует работу')
            yield press_old('✅ Сменить плательщика')
            person.sees('устарела', expected='Старая кнопка честно отвечает, что устарела')
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
            person.sees('уже', expected='Повторная просьба не предлагает пустую смену')
        stand = self.play([before, after], setup=setup)
        self.assertEqual(1, len(writes(stand, 'link')))

    def test_crash_after_invoice_write_is_found_and_pdf_is_returned(self):
        def setup(crm):
            office(crm)
            crm.crash_after_write.add(('contract_invoice', 'create_full'))
        def before(person):
            yield from open_invoice_preview(person)
            yield press('✅ Выставить общий счёт')
        def after(person):
            person.sees('Проверил Мегаплан', 'найден в единственном экземпляре', 'повторять её не нужно',
                        expected='Бот сам нашёл единственный записанный счёт')
            person.got_document(expected='После сверки пришёл PDF найденного счёта')
            yield say('/status')
            person.sees('нет выполняющихся записей', expected='Сверенная операция закрыта')
            yield press_old('✅ Выставить общий счёт')
            person.sees('устарела', expected='Повторное нажатие не выставило второй счёт')
        stand = self.play([before, after], setup=setup)
        self.assertEqual(1, len(writes(stand, 'create_full')))

    def test_crash_before_invoice_write_is_closed_as_absent(self):
        def setup(crm):
            office(crm)
            crm.crash_before_write.add(('contract_invoice', 'create_full'))
        def before(person):
            yield from open_invoice_preview(person)
            yield press('✅ Выставить общий счёт')
        def after(person):
            person.sees('подходящего счёта', 'нет', 'записи нет', 'новый предпросмотр',
                        expected='Бот сам подтвердил отсутствие записи и объяснил безопасное продолжение')
            yield say('/status')
            person.sees('нет выполняющихся записей', expected='Отсутствующая запись больше не блокирует новую попытку')
        stand = self.play([before, after], setup=setup)
        self.assertEqual([], writes(stand, 'create_full'))

    def test_two_matching_invoices_stay_blocked_and_status_has_readback_button(self):
        def setup(crm):
            office(crm)
            crm.crash_after_write.add(('contract_invoice', 'create_full'))
            crm.duplicate_after_write.add(('contract_invoice', 'create_full'))
        def before(person):
            yield from open_invoice_preview(person)
            yield press('✅ Выставить общий счёт')
        def after(person):
            person.sees('найдено несколько подходящих счетов', 'Операция не закрыта',
                        expected='Бот не угадывает между двумя счетами')
            yield say('/status')
            person.sees('нужна сверка результата')
            person.sees_button('🔍 Сверить с Мегапланом', expected='У владельца есть кнопка повторной read-only сверки')
            yield press('🔍 Сверить с Мегапланом')
            person.sees('найдено несколько подходящих счетов', expected='Кнопка повторяет только чтение и сохраняет блокировку')
        stand = self.play([before, after], setup=setup)
        self.assertEqual(1, len(writes(stand, 'create_full')))
        self.assertEqual(3, len(stand.crm.invoices))  # one fixture invoice + two matching new invoices

    def test_stage_invoice_uses_the_same_readback_route(self):
        def setup(crm):
            office(crm)
            crm.crash_after_write.add(('contract_invoice', 'create'))
        def before(person):
            yield from open_deal_by_number(person)
            yield press('📄 Документы сделки')
            yield press('🧾 Работа со счетами')
            yield press('6.4.1')
            yield press('✅ Выставить счёт')
        def after(person):
            person.sees('найден в единственном экземпляре', 'повторять её не нужно')
            person.got_document(expected='PDF этапного счёта возвращён после read-back')
            yield say('/status')
            person.sees('нет выполняющихся записей')
        stand = self.play([before, after], setup=setup)
        self.assertEqual(1, len(writes(stand, 'create')))

    def test_new_request_replaces_an_abandoned_preview(self):
        def before(person):
            yield say('Поменяй плательщика в сделке 990001 на Альфа Сервис')
        def after(person):
            yield say('Поменяй плательщика в сделке 990002 на Альфа Климат')
            person.sees('Сделка №990002', 'Новый плательщик: ООО «Альфа Климат»',
                        expected='Новая просьба словами начинает новый сценарий, а не «нажмите кнопку»')
        stand = self.play([before, after], setup=office)
        self.assertEqual([], stand.crm.writes)


if __name__ == '__main__':
    unittest.main()
