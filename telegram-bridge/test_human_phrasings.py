"""The same request in the many ways people actually say it.

Every phrasing must reach the deterministic screen of its route (no model turn),
and phrasings that lead to a write must end in exactly that write after the
confirmation button — never before it.
"""
import unittest

import human_intents
from human_qa_harness import HumanJourneyCase, press, say
from test_human_journeys import DEAL, office


READS = {
    'покажи сделку 990001': 'Сделка №990001',
    'что по сделке 990001': 'Сделка №990001',
    'открой 990001': 'Сделка №990001',
    'сделка 990001': 'Сделка №990001',
    'какая сумма у сделки 990001': '114 000,00',
    'кто исполнитель по сделке 990001?': 'Сергей Деревянко',
    'инфа по сделке 990001': 'Сделка №990001',
    'Какой статус у сделки 990002?': 'Закупка',
    'оплачена ли сделка 990001': 'Остаток по выставленным счетам',
    'сколько оплачено по 990001': 'Остаток по выставленным счетам',
    'есть долг по сделке 990001?': 'Остаток по выставленным счетам',
    'нужен счёт по 990001': 'Какой счёт выставить по сделке №990001',
    'счет на оплату по сделке 990001 сделай': 'Какой счёт выставить по сделке №990001',
    'сформируй счёт клиенту по сделке 990001': 'Какой счёт выставить по сделке №990001',
}

PAYER = (
    'смени плательщика 990001 альфа сервис',
    'плательщик по 990001 теперь Альфа Сервис',
    'в сделке 990001 платить будет альфа сервис',
    'Смени плательщика в 990001 на Альфа Сервис',
    'поменяй плательщика на ООО «Альфа Сервис» в сделке №990001',
    'поменять плательщика в сделке номер 990001 на альфа сервис',
)

STATUS = (
    'переведи сделку 990003 в закупку',
    'сделку 990003 в статус закупка',
    'поменяй статус сделки 990003 на Закупка',
)

INVOICE_FILES = ('пришли счет по сделке 990001', 'скинь счёт по 990001', 'где счёт по сделке 990001?',
                 'дай последний счет по сделке 990001')


class PhrasingTests(HumanJourneyCase, unittest.TestCase):
    def test_reads_and_menus(self):
        for phrase, expected in READS.items():
            with self.subTest(phrase=phrase):
                def journey(person, phrase=phrase, expected=expected):
                    yield say(phrase)
                    person.sees(expected, expected=f'«{phrase}» → {expected}')
                stand = self.play(journey, setup=office)
                self.assertEqual(0, len(stand.model.prompts), phrase)
                self.assertEqual([], stand.crm.writes, phrase)

    def test_payer_phrasings_end_in_one_confirmed_write(self):
        for phrase in PAYER:
            with self.subTest(phrase=phrase):
                def journey(person, phrase=phrase):
                    yield say(phrase)
                    person.sees('Новый плательщик: ООО «Альфа Сервис»', 'не записаны')
                    yield press('✅ Сменить плательщика')
                    person.sees('плательщик изменён')
                stand = self.play(journey, setup=office)
                self.assertEqual('7102', stand.crm.deals[DEAL]['payer_id'], phrase)
                self.assertEqual(0, len(stand.model.prompts), phrase)

    def test_status_phrasings_end_in_one_confirmed_write(self):
        for phrase in STATUS:
            with self.subTest(phrase=phrase):
                def journey(person, phrase=phrase):
                    yield say(phrase)
                    person.sees('Подтвердите перевод сделки №990003 в статус «Закупка»')
                    yield press('✅ Подтвердить')
                    person.sees('Закупка')
                stand = self.play(journey, setup=office)
                self.assertEqual('3', stand.crm.deals['990003']['status_id'], phrase)
                self.assertEqual(1, len(stand.crm.writes), phrase)

    def test_unknown_status_name_offers_the_real_choices(self):
        def journey(person):
            yield say('переведи сделку 990003 в статус Отгрузка')
            person.sees('«Отгрузка»', 'недоступен', 'Куда перевести')
            person.sees_button('➡️ Закупка')
        stand = self.play(journey, setup=office)
        self.assertEqual([], stand.crm.writes)

    def test_invoice_file_phrasings(self):
        for phrase in INVOICE_FILES:
            with self.subTest(phrase=phrase):
                def journey(person, phrase=phrase):
                    yield say(phrase)
                    person.got_document('311')
                self.play(journey, setup=office)

    def test_classifier_keeps_unrelated_messages_alone(self):
        for text in ('переведи 5000 монтажнику', 'Привет', 'Оплати счет', 'Какие позиции нужно закупить у Hogart?',
                     'сколько стоит сплит Haier 2,5 кВт'):
            with self.subTest(text=text):
                intent = human_intents.classify(text)
                self.assertNotIn(getattr(intent, 'name', None),
                                 (human_intents.MOVE_STATUS, human_intents.ISSUE_INVOICE, human_intents.CHANGE_PAYER))


if __name__ == '__main__':
    unittest.main()
