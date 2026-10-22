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

    def test_crash_after_invoice_write_blocks_a_second_invoice_and_says_why(self):
        def setup(crm):
            office(crm)
            crm.crash_after_write.add(('contract_invoice', 'create_full'))
        def before(person):
            yield from open_invoice_preview(person)
            yield press('✅ Выставить общий счёт')
        def after(person):
            person.sees('перезапускался', 'Клиентский счёт', 'повтор этой записи заблокирован',
                        expected='Бот сам сообщил о прерванном счёте и объяснил, что делать')
            yield say('/status')
            person.sees('нужна сверка результата', expected='/status показывает заблокированную запись')
            yield press_old('✅ Выставить общий счёт')
            person.sees('устарела', expected='Повторное нажатие не выставило второй счёт')
        stand = self.play([before, after], setup=setup)
        self.assertEqual(1, len(writes(stand, 'create_full')))

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
