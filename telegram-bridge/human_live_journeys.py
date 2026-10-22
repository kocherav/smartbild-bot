"""Human journeys on a read-only snapshot of the real CRM.

Run by the ``human`` QA profile only (the name has no ``test_`` prefix, so the
offline release gate does not require production data).  Without a verified
snapshot every case fails with the command that captures one: a journey that
was never run on real data is not reported as checked.

Registry: QA_HUMAN_REGISTRY or docs/architecture/HUMAN_JOURNEYS.json.
"""
import os
from pathlib import Path
import unittest

import human_fixtures
from human_qa_harness import HumanJourneyCase, press, press_old, say


REGISTRY = Path(os.environ.get('QA_HUMAN_REGISTRY') or
                Path(__file__).resolve().parent / 'docs' / 'architecture' / 'HUMAN_JOURNEYS.json')


def money(value):
    return f'{float(value):,.2f}'.replace(',', ' ').replace('.', ',')


class LiveSnapshotJourneys(HumanJourneyCase, unittest.TestCase):
    def setUp(self):
        self.snapshot, problem = human_fixtures.verified_snapshot(REGISTRY)
        if problem:
            self.fail('Нет проверенного снимка CRM: ' + problem)
        self.deals = self.snapshot.get('deals') or []

    def setup(self, crm):
        human_fixtures.load(crm, self.snapshot)

    def pick(self, condition, need):
        found = next((item for item in self.deals if condition(item)), None)
        if not found:
            self.fail(f'В снимке нет сделки, где {need}. Добавьте такую сделку: qa_agent.py capture --deal <номер>')
        return found

    def test_read_deal(self):
        item = self.pick(lambda x: x['ledger'], 'есть позиции')
        deal = item['deal']
        total = sum(float(r.get('qty') or 0) * float(r.get('sell_price') or 0) for r in item['ledger'])
        def journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('🔢 Найти по номеру')
            yield say(deal['id'])
            person.sees(f"Сделка №{deal['id']}", deal.get('client') or '', expected='Открыта карточка реальной сделки')
            yield press('📋 Основное')
            yield press('📄 Позиции сделки')
            person.sees(f"Итого: {money(total)}", expected='Итог позиций совпал с CRM')
            person.got_document(f"Позиции сделки {deal['id']}")
        self.play(journey, setup=self.setup)

    def test_change_payer(self):
        item = self.pick(lambda x: len(x['payers']) >= 2, 'у клиента два плательщика или больше')
        target = next(p for p in item['payers'] if not p.get('selected'))
        deal_id = item['deal']['id']
        def journey(person):
            yield say(f"Поменяй плательщика в сделке {deal_id} на {target['name']}")
            person.sees(target['name'], 'не записаны', expected='Показан предпросмотр смены плательщика')
            yield press('✅ Сменить плательщика')
            person.sees('плательщик изменён', expected='Смена подтверждена обратным чтением')
        stand = self.play(journey, setup=self.setup)
        self.assertEqual(target['id'], stand.crm.deals[deal_id]['payer_id'])

    def test_get_invoice(self):
        item = self.pick(lambda x: x['invoices'], 'есть счёт')
        def journey(person):
            yield say(f"Пришли счёт по сделке {item['deal']['id']}")
            person.got_document(expected='Пришёл PDF последнего счёта')
        self.play(journey, setup=self.setup)

    def test_issue_full_invoice(self):
        item = self.pick(lambda x: x['ledger'] and any(p.get('selected') for p in x['payers']),
                         'выбран плательщик и есть позиции')
        deal_id = item['deal']['id']
        def journey(person):
            yield say(f'Выстави счёт по сделке {deal_id}')
            yield press('📋 Общий счёт по спецификации')
            person.sees('Плательщик', 'Сумма', expected='Предпросмотр счёта показан')
            yield press('✅ Выставить общий счёт')
            person.sees('выставлен')
            person.got_document()
        stand = self.play(journey, setup=self.setup)
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'create_full']))

    def test_move_status(self):
        item = self.pick(lambda x: any(t.get('enabled') for t in x['deal'].get('transitions') or []),
                         'доступен перевод статуса')
        deal = item['deal']
        target = next(t for t in deal['transitions'] if t.get('enabled'))
        def journey(person):
            yield press('🤝 Сделки')
            yield press('🔎 Найти сделку')
            yield press('🔢 Найти по номеру')
            yield say(deal['id'])
            yield press('📋 Основное')
            yield press('🔄 Изменить статус')
            yield press('➡️ ' + target['name'])
            yield press('✅ Подтвердить')
            person.sees(target['name'], expected='Бот подтвердил новый статус')
        self.play(journey, setup=self.setup)

    def test_create_deal_for_real_client(self):
        item = self.pick(lambda x: x.get('client_id') and x.get('client_name'), 'известен клиент')
        name = item['client_name']
        block = ('CREATE_MEGAPLAN_DEAL_BEGIN\n{"client_name": %s, "description": "QA-проверка",'
                 ' "items": [{"name": "Монтаж сплит-системы", "qty": 1, "unit_price": 14000}]}\n'
                 'CREATE_MEGAPLAN_DEAL_END') % __import__('json').dumps(name, ensure_ascii=False)
        label = f"Клиент ID {item['client_id']} — {name}"
        def journey(person):
            yield press('🤝 Сделки')
            yield press('➕ Создать сделку')
            yield say('QA-проверка')
            yield say(name)
            person.sees_button(label, expected='Реальный клиент найден по названию')
            yield press(label)
            yield say('Монтаж сплит-системы 1 шт 14000')
            if 'НДС 22%' in person.visible_buttons():
                yield press('НДС 22%')
            yield press('✅ Создать подтверждённую сделку')
            person.sees('Сделка создана')
        stand = self.play(journey, setup=self.setup, model_rules=[('Монтаж сплит-системы 1 шт', block)])
        created = [w for w in stand.crm.writes if w['script'] == 'megaplan_api']
        self.assertEqual(str(item['client_id']), str(created[0]['spec'].get('client_id')))


    def test_prepare_contract(self):
        item = self.pick(lambda x: x['ledger'] and any(p.get('selected') for p in x['payers']),
                         'выбран плательщик и есть позиции')
        deal_id = item['deal']['id']
        total = sum(float(r.get('qty') or 0) * float(r.get('sell_price') or 0) for r in item['ledger'])
        answers = (('ФИО подписанта', say('Иванов Иван Иванович')), ('должность', say('Генеральный директор')),
                   ('адрес объекта', say('Москва, ул. Тестовая, 1')), ('дату договора', say('23.10.2026')))
        def journey(person):
            yield say(f'Покажи сделку {deal_id}')
            yield press('📄 Документы сделки')
            yield press('📑 Работа с договором')
            yield press('👁 Проверить данные договора')
            for _ in range(6):
                screen = person.screen_text()
                if 'Договор №' in screen:
                    break
                if 'Устав' in person.visible_buttons():
                    yield press('Устав')
                    continue
                answer = next((action for prompt, action in answers if prompt in screen), None)
                person.check('Бот задаёт понятный вопрос о данных договора', screen, answer)
                yield answer
            person.sees('Договор №', money(total), expected='Предпросмотр договора с суммой сделки')
            yield press('✅ Сформировать договор')
            person.got_document('.docx')
            person.got_document('.pdf')
            yield press('✅ Загрузить договоры в сделку')
            person.sees('загружены')
        stand = self.play(journey, setup=self.setup)
        self.assertEqual(1, len([w for w in stand.crm.writes if w['action'] == 'upload_contracts']))

    def test_proposal(self):
        item = self.pick(lambda x: x['ledger'], 'есть позиции')
        def journey(person):
            yield say(f"Сделай КП по сделке {item['deal']['id']}")
            person.sees('Кому адресовать')
            yield say('Алексей')
            person.got_document('КП')
            person.sees(f"{len(item['ledger'])} позиций", expected='КП содержит все позиции сделки')
        self.play(journey, setup=self.setup)

    def test_restart_during_payer_change(self):
        item = self.pick(lambda x: len(x['payers']) >= 2, 'у клиента два плательщика или больше')
        target = next(p for p in item['payers'] if not p.get('selected'))
        deal_id = item['deal']['id']
        def setup(crm):
            self.setup(crm)
            crm.crash_after_write.add(('payer_manager', 'link'))
        def before(person):
            yield say(f"Поменяй плательщика в сделке {deal_id} на {target['name']}")
            yield press('✅ Сменить плательщика')
        def after(person):
            person.sees('Проверил Мегаплан', 'Повторять не нужно', expected='После сбоя бот сам сверил запись')
            yield press_old('✅ Сменить плательщика')
            person.sees('устарела', expected='Повтор записи невозможен')
        stand = self.play([before, after], setup=setup)
        self.assertEqual(1, len([w for w in stand.crm.writes if w['script'] == 'payer_manager']))


if __name__ == '__main__':
    unittest.main()
