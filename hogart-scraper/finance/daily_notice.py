"""Concrete import receipts and outstanding owner questions."""
import json, hashlib, urllib.request, datetime as dt, subprocess, sys
from pathlib import Path
from zoneinfo import ZoneInfo
from ledger import ROOT


def money(value):
    return f'{value:,.2f}'.replace(',', ' ').replace('.', ',') + ' ₽'


def import_notice(status, root=ROOT):
    imports = status.get('imports') or []
    changes = sum(x.get('new', 0) for x in imports)
    repeated = sum(x.get('repeated', 0) for x in imports)
    lines = [f'Выписка обработана: {changes} новых операций добавлено в реестр движения денег; {repeated} повторов пропущено.']
    companies = {a['account']: a['company'] for a in status.get('accounts', [])}
    details = {(s['account'], s['start'], s['end']) for entry in imports for s in entry.get('statement_details', [])}
    for account, start, end in sorted(details):
        lines.append(f'{companies.get(account, "Организация не определена")}, счёт …{account[-4:]}: {start} — {end}.')
    lines.append('Обороты и остатки импортированных выписок сошлись с банковскими данными.')
    ids = {oid for entry in imports for oid in entry.get('new_ids', [])}
    ledger_path = root / 'reports/ledger.json'
    rows = json.loads(ledger_path.read_text()) if ledger_path.exists() else []
    added = [row for row in rows if row['id'] in ids]
    if added:
        lines.append('\nНовые операции:')
        for row in added:
            direction = 'поступление' if row['direction'] == 'in' else 'списание'
            line = f'• {row["company"]}, {row["date"]}, №{row["number"]}: {row["counterparty"]}, {direction} {money(row["amount_cents"] / 100)}.'
            line += f' Статья: {row["category"]}. {row["status"]}.'
            if row.get('project'):
                line += f' Объект: {row["project"]}.'
            if row.get('crm_operations'):
                line += f' Связанные операции Мегаплана: {row["crm_operations"]}.'
            if row.get('flags'):
                line += ' Осталось выяснить: ' + '; '.join(row['flags']) + '.'
            lines.append(line)
    if len(added) != changes:
        lines.append('Полный состав новых операций в этой сводке не восстановлен; подробности — на листе «Операции» отчёта.')
    lines.append('Добавление в реестр выписок само по себе не означает проведение платежа в Мегаплане.')
    report = status.get('report')
    if not report:
        lines.append('\nОбновление Excel-отчёта не подтверждено. Список оставшихся вопросов сейчас не подтверждён.')
        return '\n'.join(lines)
    lines.append('\nОбновлён отчёт «Разнесение_выписок.xlsx» — он приложен к уведомлению. Лист «Операции» — платежи и их статусы; «Контроль» — проверка остатков.')
    questions = report.get('owner_questions')
    if questions:
        lines.append(f'\nНужен ваш ответ — {len(questions)} вопрос(а), лист «Вам» по всему реестру, включая прежние выписки:')
        lines.extend(f'{i}. {q}' for i, q in enumerate(questions, 1))
        lines.append('Ответьте сообщением в боте, указав счёт, платёж или контрагента из вопроса.')
    elif questions == []:
        lines.append('\nОткрытых вопросов к вам нет. От вас сейчас действий не требуется.')
    else:
        lines.append('\nСписок вопросов к вам не получен; отсутствие вопросов не подтверждено.')
    queue = report.get('assistant_queue')
    if queue:
        lines.append(f'\nНа дальнейшую проверку ассистенту: {sum(q["count"] for q in queue)} операций, {len(queue)} задач по всему реестру. Они перечислены на листе «Рабочая очередь»; это не дополнительные вопросы к вам.')
        for q in queue[:5]:
            lines.append(f'• {q["group"]}: {q["company"]}, {q["counterparty"]} — {q["count"]} операций, {money(q["amount"])}. {q["reason"]}.')
        if len(queue) > 5:
            lines.append(f'Остальные {len(queue)-5} задач — в приложенном отчёте.')
    elif queue == []:
        lines.append('Рабочая очередь проверки пуста.')
    return '\n'.join(lines)


def notify_status(status):
    state_path = ROOT / 'data/notice_state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    now = dt.datetime.now(ZoneInfo('Europe/Moscow'))
    changes = sum(x.get('new', 0) for x in status['imports'])
    missing = [a for a in status['accounts'] if a['owner_confirmed'] and a['needs_statement']]
    text = key = None
    if changes:
        key = 'import:' + ','.join(x['archive'] for x in status['imports'])
        text = import_notice(status)
    if status['errors']:
        key = (key or '') + 'error:' + hashlib.sha256(json.dumps(status['errors'], sort_keys=True).encode()).hexdigest()
        errors = '\n'.join(f'• Этап {x["stage"]}: {x.get("reason") or x.get("error") or "требуется проверка"}' for x in status['errors'])
        text = (text + '\n\n' if text else '') + 'Не завершено из-за ошибок:\n' + errors
    elif not changes and missing:
        key = 'missing:' + now.date().isoformat()
        text = 'При ежедневной проверке полная выписка за вчера не найдена: ' + ', '.join(a['company'] for a in missing) + '. Следующая автоматическая проверка — завтра в 10:30 МСК; позднюю выписку можно прислать в бот вручную.'
    if not text or key in state:
        return
    # Deliver the referenced report before claiming it is attached.
    report = status.get('report') or {}
    if changes and report.get('xlsx'):
        result = subprocess.run([sys.executable, str(ROOT / 'send_report.py'),
                                 'Разнесение выписок: «Вам» — ваши вопросы; «Рабочая очередь» — оставшаяся проверка.', report['xlsx']],
                                capture_output=True, text=True, timeout=60, check=True)
        if not json.loads(result.stdout).get('sent'):
            raise RuntimeError('Statement report delivery failed')
    env = {}
    for line in Path('/home/kocher.av/telegram-bridge/.env').read_text().splitlines():
        if '=' in line and not line.lstrip().startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    for offset in range(0, len(text), 3500):
        req = urllib.request.Request('https://api.telegram.org/bot' + env['TELEGRAM_BOT_TOKEN'] + '/sendMessage',
            data=json.dumps({'chat_id': env['TELEGRAM_CHAT_ID'], 'text': text[offset:offset+3500]}, ensure_ascii=False).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            if not json.load(response).get('ok'):
                raise RuntimeError('Bot notification failed')
    state[key] = now.isoformat()
    state_path.write_text(json.dumps(state, ensure_ascii=False))
