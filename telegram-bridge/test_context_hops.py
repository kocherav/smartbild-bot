"""Context hops: start an action in deal A, move to deal B, try to continue (owner 07.11).

«Придумать тестовые маршруты, в которых контекст может теряться и бот будет прыгать в
другой контекст». Every combination of

* an action left waiting in deal A (preview before a write, or a question in the middle),
* a way the person moves to deal B (number, phrase, read request, search, menu, list…),
* a way the old action could be continued (old button, typed «да», the expected answer,
  a file),

must end with **no write to deal A after the move**. The stand's general invariant
(``Stand.check_write_context``) additionally fails any write to a deal that is not the open
one. The matrix is generated, so a new flow or switch is one line.
"""
import os
import tempfile
import unittest

from human_qa_harness import HumanJourneyCase, press, press_old, reply, say, send_file
from test_human_journeys import DEAL as A, office

B = '990002'


def _contract_answers(person):
    for _ in range(6):
        text = person.screen_text()
        if 'Договор №' in text:
            return
        if 'ФИО подписанта' in text:
            yield say('Петров Иван Сергеевич')
        elif 'должность' in text:
            yield say('Генеральный директор')
        elif 'Устав' in person.visible_buttons():
            yield press('Устав')
        else:
            return


def _file():
    folder = tempfile.mkdtemp(prefix='qa-hop-')
    path = os.path.join(folder, 'Проект.pdf')
    with open(path, 'wb') as handle:
        handle.write(b'%PDF-1.4 hop')
    return path


# name: (steps in A, button that would write, extra continuation or None)
FLOWS = {
    'invoice_full': (lambda p: iter([say(A), press('🧾 Выставить счёт'), press('📋 Общий счёт по спецификации')]),
                     '✅ Выставить общий счёт', None),
    'invoice_stage': (lambda p: iter([say(A), press('📄 Документы сделки'), press('🧾 Работа со счетами'),
                                      press('6.4.1')]), '✅ Выставить счёт', None),
    'contract': (lambda p: _chain([say(A), press('📄 Документы сделки'), press('📑 Работа с договором'),
                                   press('👁 Проверить данные договора')], _contract_answers, p),
                 '✅ Сформировать и загрузить Word и PDF', None),
    'contract_signer_question': (lambda p: iter([say(A), press('📄 Документы сделки'),
                                                 press('📑 Работа с договором'),
                                                 press('👁 Проверить данные договора')]),
                                 None, say('Петров Иван Сергеевич')),
    'contract_subject': (lambda p: iter([say(A), say('Измени предмет договора на монтаж вентиляции')]),
                         '✅ Записать предмет договора', None),
    'payer': (lambda p: iter([say(A), say('Смени плательщика на Альфа Сервис')]), '✅ Сменить плательщика', None),
    'executor': (lambda p: iter([say(f'Назначь исполнителем сделки {A} Смирнова'),
                                 press('Сотрудник ID 1000011 — Алексей Смирнов')]),
                 '✅ Назначить исполнителя', None),
    'executor_choice': (lambda p: iter([say(f'Назначь исполнителем сделки {A} Смирнова')]),
                        None, press_old('Сотрудник ID 1000011 — Алексей Смирнов')),
    'status': (lambda p: iter([say(A), say('Переведи сделку в Закупку')]), '✅ Подтвердить', None),
    'proposal': (lambda p: iter([say(f'Сделай КП по сделке {A}'), say('Алексей')]), '✅ Создать PDF КП', None),
    'proposal_recipient_question': (lambda p: iter([say(f'Сделай КП по сделке {A}')]), None, say('Алексей')),
    'economics_save': (lambda p: iter([say(A), press('💰 Экономика')]), '💾 Сохранить расчёт в CRM', None),
    'project_upload': (lambda p: iter([say(A), press('🧰 Монтаж сделки'), press('📐 Приложить проект'),
                                       press('📤 Загрузить новый файл')]), None, 'FILE'),
}


def _chain(steps, then, person):
    for step in steps:
        yield step
    yield from then(person)


# Switches that need deal B's card earlier in the chat open it first (prelude).
PRELUDE = {'reply_to_b_card': [say(B)]}

SWITCHES = {
    'number': lambda: [say(B)],
    'show_phrase': lambda: [say(f'покажи сделку {B}')],
    'payment_question': lambda: [say(f'Оплачена ли сделка {B}?')],
    'economics_phrase': lambda: [say(f'Покажи экономику по сделке {B}')],
    'main_menu_then_number': lambda: [say('/menu'), say(B)],
    'search_line': lambda: [press('🤝 Сделки'), press('🔎 Найти сделку'), say('склад Химки')],
    'invoice_phrase': lambda: [say(f'пришли счёт по сделке {B}')],
    'reply_to_b_card': lambda: [reply('покажи эту сделку', to=f'Сделка №{B}')],
    'find_then_act': lambda: [say('найди сделку склад Химки и выстави счёт'),
                              press_old('№990002 · Вентиляция склада')],
    'search_list_choice': lambda: [press('🤝 Сделки'), press('🔎 Найти сделку'), press('🔎 Найти по клиенту'),
                                   say('Альфа Климат'), press_old('№990002 · Вентиляция склада')],
    'restart_then_number': lambda: ['RESTART', say(B)],
    'create_new_deal': lambda: [say('Создай сделку для клиента Альфа Климат: Сплит-система Haier AS35 — 2 шт по 52000; монтаж — 2 шт по 14000')],
    'compare_two_deals': lambda: [say(f'сравни сделки {A} и {B}')],
}

CREATE_BLOCK = ('Черновик готов.\nCREATE_MEGAPLAN_DEAL_BEGIN\n'
                '{"client_name": "ООО «Альфа Климат»", "description": "Переговорная", '
                '"selling_company_id": "cliwell", "tax_mode": "5", '
                '"items": [{"name": "Сплит-система Haier AS35", "qty": 2, "unit_price": 52000}, '
                '{"name": "Монтаж сплит-системы", "qty": 2, "unit_price": 14000}]}\n'
                'CREATE_MEGAPLAN_DEAL_END')

CONTINUE = {
    'old_button': 'button',
    'typed_yes': 'yes',
    'expected_answer': 'extra',
    'file': 'file',
}


def _writes_to(stand, deal, start):
    return [w for w in stand.crm.writes[start:]
            if str((w['spec'] or {}).get('deal_id') or (w['spec'] or {}).get('dealId') or '') == deal]


class ContextHopMatrix(HumanJourneyCase, unittest.TestCase):
    maxDiff = None


def _make(flow_name, switch_name, cont_name):
    steps, confirm, extra = FLOWS[flow_name]

    def test(self):
        marks = {}
        switch = SWITCHES[switch_name]()
        cut = switch.index('RESTART') if 'RESTART' in switch else None

        def first(person):
            for step in PRELUDE.get(switch_name, []):
                yield step
            yield from steps(person)
            if confirm:
                person.sees_button(confirm, expected=f'В сделке {A} ждёт подтверждение')
            marks['switch'] = len(person.stand.crm.writes)
            if cut is None:
                yield from second(person)

        def second(person):
            for step in (switch[cut + 1:] if cut is not None else switch):
                yield step
            if cont_name == 'button':
                yield press_old(confirm)
            elif cont_name == 'yes':
                yield say('да')
            elif cont_name == 'file' or extra == 'FILE':
                yield send_file(_file())
            else:
                yield extra
        stand = self.play([first, second] if cut is not None else first, setup=office,
                          model_rules=[('Сплит-система Haier AS35', CREATE_BLOCK)])
        hopped = _writes_to(stand, A, marks.get('switch', 0))
        self.assertEqual([], hopped, f'{flow_name} → {switch_name} → {cont_name}: запись в прежнюю сделку {A}')

    return test


for _flow, (_steps, _confirm, _extra) in FLOWS.items():
    for _switch in SWITCHES:
        for _cont_name, _cont in CONTINUE.items():
            if _cont == 'button' and not _confirm:
                continue
            if _cont == 'extra' and not _extra:
                continue
            if _cont == 'file' and _extra == 'FILE':
                continue
            setattr(ContextHopMatrix, f'test_{_flow}__{_switch}__{_cont_name}', _make(_flow, _switch, _cont))


if __name__ == '__main__':
    unittest.main()
