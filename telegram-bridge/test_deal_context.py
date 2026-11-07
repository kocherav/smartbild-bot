"""One open deal per chat (incident 865/888, 07.11; deal 905, 06.11).

Owner 07.11: «Если идёт общение про сделку №100500, то все действия происходят только со
сделкой 100500». Each journey switches between two deals in one chat and counts CRM writes.
"""
import os
import tempfile
import unittest

import deal_context
from human_qa_harness import HumanJourneyCase, press, press_old, say, send_file
from test_human_journeys import DEAL, office

OTHER = '990002'


def project_file(name):
    folder = tempfile.mkdtemp(prefix='qa-project-')
    path = os.path.join(folder, name)
    with open(path, 'wb') as handle:
        handle.write(b'%PDF-1.4 project ' + name.encode())
    return path


def attaches(stand):
    return [w['spec'] for w in stand.crm.writes if w['action'] == 'attach_project']


class SwitchRuleTest(unittest.TestCase):
    def test_switch_drops_everything_of_the_previous_deal(self):
        state = {'current_deal_id': '888', 'installation_deal_id': '888', 'contract_deal_id': '888',
                 'contract_preview': {'total': 1}, 'invoice_full_preview': {'x': 1},
                 'installation_project_upload_deal_id': '888', 'pending': 'installation_project_upload',
                 'proposal_draft': {'deal_id': '888'}, 'suspended_payer_deal_id': '888',
                 'supplier_invoice_queue': [1], 'deal_create_spec': {'a': 1}, 'bank_transaction_id': 't'}
        values = deal_context.switch_values(state, {'current_deal_id': '865'})
        for key in ('installation_deal_id', 'contract_deal_id', 'contract_preview', 'invoice_full_preview',
                    'installation_project_upload_deal_id', 'pending'):
            self.assertIn(key, values, key)
            self.assertIsNone(values[key], key)
        for kept in ('proposal_draft', 'suspended_payer_deal_id', 'supplier_invoice_queue',
                     'deal_create_spec', 'bank_transaction_id'):
            self.assertNotIn(kept, values, kept)

    def test_same_deal_or_no_switch_changes_nothing(self):
        state = {'current_deal_id': '865', 'installation_deal_id': '865'}
        self.assertEqual({'current_deal_id': '865'}, deal_context.switch_values(state, {'current_deal_id': '865'}))
        self.assertEqual({'pending': None}, deal_context.switch_values(state, {'pending': None}))

    def test_opening_a_deal_from_no_deal_drops_a_foreign_bound_id(self):
        # The exact 865/888 shape: no card was open, a forgotten 888 installation id remained.
        values = deal_context.switch_values({'installation_deal_id': '888'}, {'current_deal_id': '865'})
        self.assertIsNone(values['installation_deal_id'])

    def test_open_card_wins_over_a_bound_id(self):
        self.assertEqual('865', deal_context.target({'current_deal_id': '865', 'installation_deal_id': '888'},
                                                     'installation_deal_id'))
        self.assertEqual('888', deal_context.target({'installation_deal_id': '888'}, 'installation_deal_id'))

    def test_button_of_another_deal_is_stale_but_navigation_is_not(self):
        state = {'current_deal_id': '865'}
        self.assertEqual('888', deal_context.stale_button('✅ Выставить общий счёт', '888', state))
        self.assertIsNone(deal_context.stale_button('№888 · Ильинка', '888', state))
        self.assertIsNone(deal_context.stale_button('❌ Отмена', '888', state))
        self.assertIsNone(deal_context.stale_button('✅ Выставить общий счёт', '865', state))
        self.assertIsNone(deal_context.stale_button('✅ Выставить общий счёт', None, state))


class ProjectUploadContextJourneys(HumanJourneyCase, unittest.TestCase):
    """Card items 1–3: 888 → 865, mirror 865 → 888, switch between the button and the file."""

    def _start_project(self, person):
        yield press('🧰 Монтаж сделки')
        yield press('📐 Приложить проект')
        yield press('📤 Загрузить новый файл')

    def _switch_and_upload(self, first, second):
        def journey(person):
            yield say(first)
            yield press('🧰 Монтаж сделки')
            yield press('📐 Приложить проект')   # binds the installation context to `first`
            # The person goes to the other deal through a phrase, not the deal list
            # (the path that kept the old installation id before).
            yield say(f'покажи сделку {second}')
            person.sees(f'Сделка №{second}', expected='Открыта вторая сделка')
            yield from self._start_project(person)
            person.sees(f'Пришлите файл проекта для сделки №{second}',
                        expected='Бот назвал сделку, к которой будет приложен файл')
            yield send_file(project_file('ЖК Реноме.pdf'))
            person.sees(f'сделки №{second}', expected='Ответ о записи называет сделку')
        stand = self.play(journey, setup=office)
        done = attaches(stand)
        self.assertEqual(1, len(done), 'ровно одна запись проекта')
        self.assertEqual(second, str(done[0]['deal_id']), 'файл только в открытой сделке')
        self.assertNotIn(first, stand.crm.__dict__.get('projects', {}), 'в прежнюю сделку ничего не записано')

    def test_888_then_865(self):
        self._switch_and_upload(OTHER, DEAL)

    def test_865_then_888(self):
        self._switch_and_upload(DEAL, OTHER)

    def test_switch_between_upload_button_and_file_attaches_nothing(self):
        def journey(person):
            yield say(DEAL)
            yield from self._start_project(person)
            yield say(f'покажи сделку {OTHER}')
            person.sees(f'Сделка №{OTHER}')
            yield send_file(project_file('Ильинка.pdf'))
            person.not_sees('Файл сохранён как проект', expected='Файл не привязан молча ни к одной сделке')
        stand = self.play(journey, setup=office)
        self.assertEqual([], attaches(stand), 'после переключения файл никуда не записан')


    def test_two_files_in_a_row_make_one_version_of_the_open_deal(self):
        def journey(person):
            yield say(DEAL)
            yield from self._start_project(person)
            yield send_file(project_file('Реноме.pdf'))
            yield send_file(project_file('Реноме-копия.pdf'))
        stand = self.play(journey, setup=office)
        done = attaches(stand)
        self.assertEqual(1, len(done), 'второй файл без новой команды не создаёт версию')
        self.assertEqual(DEAL, str(done[0]['deal_id']))


class StaleActionJourneys(HumanJourneyCase, unittest.TestCase):
    """Card item 5 and the general rule: confirmations of deal A cannot act while B is open."""

    def test_old_invoice_button_after_switch_does_nothing(self):
        def journey(person):
            yield say(DEAL)
            yield press('🧾 Выставить счёт')
            yield press('📋 Общий счёт по спецификации')
            person.sees_button('✅ Выставить общий счёт')
            yield say(OTHER)
            person.sees(f'Сделка №{OTHER}')
            yield press_old('✅ Выставить общий счёт')
            person.not_sees('Счёт выставлен', expected='Старая кнопка сделки A не выставила счёт')
        stand = self.play(journey, setup=office)
        self.assertEqual([], [w for w in stand.crm.writes if w['action'] == 'create_full'])

    def test_typed_yes_after_switch_does_not_confirm_the_old_preview(self):
        def journey(person):
            yield say(DEAL)
            yield press('🧾 Выставить счёт')
            yield press('📋 Общий счёт по спецификации')
            yield say(f'покажи сделку {OTHER}')
            yield say('да')
        stand = self.play(journey, setup=office)
        self.assertEqual([], [w for w in stand.crm.writes if w['action'] == 'create_full'])

    def test_named_deal_becomes_the_open_deal_for_following_requests(self):
        def journey(person):
            yield say(DEAL)
            yield say(f'Покажи экономику по сделке {OTHER}')
            person.sees(f'Экономика сделки №{OTHER}', expected='Экономика по названной сделке')
            yield say('Оплачена ли сделка?')
            person.sees(f'Сделка №{OTHER}', expected='Следующий вопрос без номера — о названной сделке, не о прежней')
            person.not_sees(f'Сделка №{DEAL} —', expected='Прежняя сделка не подставлена')
        self.play(journey, setup=office)

    def test_assistant_is_told_the_open_deal(self):
        def journey(person):
            yield say(OTHER)
            yield say('расскажи что по ней известно из переписки')
        stand = self.play(journey, setup=office)
        self.assertTrue(stand.model.prompts, 'вопрос ушёл ассистенту')
        self.assertIn(f'открыта сделка №{OTHER}', stand.model.prompts[-1])
        self.assertIn('Номера сделок из прошлых сообщений', stand.model.prompts[-1])


if __name__ == '__main__':
    unittest.main()
