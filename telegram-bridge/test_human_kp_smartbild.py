"""Automation proposals in the SmartBild template, as the owner uses them (11.11)."""
import unittest

from human_qa_harness import HumanJourneyCase, press, say
from test_human_journeys import DEAL, office

AUTOMATION = '990005'


def with_automation_deal(crm):
    office(crm)
    crm.add_deal(AUTOMATION, '501', 'Автоматизация квартиры', status_id='2', address='Москва, Шелепиха',
                 payer_id='7101', positions=[('Iridi HS Server', 1, 93170, 70000, None),
                                             ('Контроллер централизованного управления Daikin DCM-BMS-01', 1, 267450, 200000, None),
                                             ('Пусконаладка системы автоматизации', 1, 53000, None, 20000)])


def proposals(stand):
    return [w['spec'] for w in stand.crm.writes if w['script'] == 'deal_proposal']


class SmartBildProposalJourneys(HumanJourneyCase, unittest.TestCase):
    def test_automation_deal_is_suggested_in_smartbild_with_its_modules(self):
        def journey(person):
            yield say(f'Сделай КП по сделке {AUTOMATION}')
            yield say('Сергей')
            person.sees('Оформление: КП SmartBild по автоматизации', 'Модули: Климат, Уведомления, Сценарии',
                        expected='По составу сделки предложен шаблон SmartBild и модули')
            person.sees_button('☑ Климат'); person.sees_button('☐ Свет и шторы')
            yield press('✅ Создать PDF КП')
            person.got_document('КП SmartBild', expected='Пришёл PDF в шаблоне SmartBild')
            person.got_document('.docx', expected='Пришёл Word для правок')
        stand = self.play(journey, setup=with_automation_deal)
        spec = proposals(stand)
        self.assertEqual(1, len(spec), 'одно КП')
        self.assertEqual('smartbild', spec[0]['template'])
        self.assertEqual(['climate', 'telegram', 'scenes'], spec[0]['modules'])

    def test_owner_edits_modules_before_the_pdf(self):
        def journey(person):
            yield say(f'Сделай КП по сделке {AUTOMATION}')
            yield say('Сергей')
            yield press('☐ Свет и шторы')
            person.sees('Модули: Свет и шторы, Климат, Уведомления, Сценарии', expected='Модуль добавлен')
            yield press('☑ Уведомления')
            person.sees('Модули: Свет и шторы, Климат, Сценарии', expected='Модуль убран')
            yield press('✅ Создать PDF КП')
        stand = self.play(journey, setup=with_automation_deal)
        self.assertEqual(['light', 'climate', 'scenes'], sorted(proposals(stand)[0]['modules'],
                                                                 key=['light', 'climate', 'media', 'telegram', 'scenes'].index))

    def test_owner_can_switch_an_automation_deal_to_the_classic_proposal(self):
        def journey(person):
            yield say(f'Сделай КП по сделке {AUTOMATION}')
            yield say('Сергей')
            yield press('📄 Обычный КП')
            person.sees('Оформление: обычный КП КЛИВЭЛ', expected='Переключено на обычный КП')
            yield press('✅ Создать PDF КП')
        stand = self.play(journey, setup=with_automation_deal)
        self.assertNotEqual('smartbild', proposals(stand)[0].get('template'))

    def test_ordinary_deal_stays_classic_but_can_use_the_template(self):
        def journey(person):
            yield say(f'Сделай КП по сделке {DEAL}')
            yield say('Алексей')
            person.sees('Оформление: обычный КП КЛИВЭЛ', expected='Обычная сделка — обычный КП')
            person.sees_button('🎨 Оформить в шаблоне SmartBild')
            yield press('🎨 Оформить в шаблоне SmartBild')
            person.sees('Оформление: КП SmartBild по автоматизации', expected='Владелец может выбрать шаблон вручную')
            yield press('✅ Создать PDF КП')
        stand = self.play(journey, setup=office)
        self.assertEqual('smartbild', proposals(stand)[0]['template'])

    def test_typed_yes_still_confirms_with_module_buttons_on_screen(self):
        def journey(person):
            yield say(f'Сделай КП по сделке {AUTOMATION}')
            yield say('Сергей')
            yield say('да')
            person.got_document('КП SmartBild')
        stand = self.play(journey, setup=with_automation_deal)
        self.assertEqual(1, len(proposals(stand)))
        self.assertEqual(0, len(stand.model.prompts))


if __name__ == '__main__':
    unittest.main()
