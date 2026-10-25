"""Tester ideas the owner decides on with one button (owner decision 25.10).

An idea comes from the night AI judge (``ideas`` in a QA run).  The digest shows
each new idea with «✅ Берём IDEA-…» / «🚫 Не надо IDEA-…».  A taken idea is
handed to the developer with the same rules as a Git handoff task: code only
in the branch ``handoff/IDEA-…``, a report in ``handoff/outbox`` on main, and a
person merges.  On Fridays the owner gets the week's ideas and their fate.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import tempfile


BASE = Path(__file__).resolve().parent
STATE = BASE / 'qa_ideas_state.json'
VALUE_RANK = {'высокая': 0, 'средняя': 1, 'низкая': 2}
STATUS_WORDS = {'proposed': 'ждёт вашего решения', 'taken': 'взята, очередь разработчика',
                'running': 'у разработчика', 'done': 'сделана в ветке, ждёт проверки и выпуска',
                'failed': 'разработчик не справился — тестировщик разберёт', 'declined': 'не берём'}


def utc_now():
    return dt.datetime.now(dt.timezone.utc)


def _key(title):
    return ' '.join(str(title or '').casefold().replace('ё', 'е').split())


def idea_id(title):
    return 'IDEA-' + hashlib.sha256(_key(title).encode()).hexdigest()[:8].upper()


def _path(path):
    # Resolved at call time: a default argument would freeze the module path at import.
    return Path(path) if path is not None else STATE


def read(path=None):
    try:
        value = json.loads(_path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'version': 1, 'ideas': {}}
    if not isinstance(value, dict) or not isinstance(value.get('ideas'), dict):
        raise ValueError('повреждён qa_ideas_state.json')
    return value


def save(state, path=None):
    path = _path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.qa-ideas-', dir=path.parent)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def recent(qa_state, now=None, hours=24):
    """Ideas from QA runs of the last ``hours``, one per title, most valuable first."""
    now = now or utc_now()
    seen, ideas = set(), []
    for run in qa_state.get('runs') or []:
        try:
            fresh = now - dt.datetime.fromisoformat(run['at']) <= dt.timedelta(hours=hours)
        except (KeyError, ValueError, TypeError):
            continue
        for idea in (run.get('ideas') or []) if fresh else []:
            key = _key(idea.get('title'))
            if key and key not in seen:
                seen.add(key)
                ideas.append(idea)
    return sorted(ideas, key=lambda idea: VALUE_RANK.get(str(idea.get('value') or '').casefold(), 3))


def register(ideas, path=None, now=None):
    """Remember new ideas; returns those still waiting for the owner, in the given order."""
    now = (now or utc_now()).isoformat(timespec='seconds')
    state = read(path)
    waiting = []
    for idea in ideas:
        ident = idea_id(idea.get('title'))
        record = state['ideas'].get(ident)
        if record is None:
            record = state['ideas'][ident] = {
                'id': ident, 'title': str(idea.get('title') or ''), 'why': str(idea.get('why') or ''),
                'how': str(idea.get('how') or ''), 'value': str(idea.get('value') or ''),
                'mission': str(idea.get('mission') or ''), 'status': 'proposed',
                'first_seen': now, 'seen': 0}
        record['seen'] = int(record.get('seen') or 0) + 1
        record['last_seen'] = now
        if record['status'] == 'proposed':
            waiting.append(record)
    save(state, path)
    return waiting


def pending(path=None):
    ideas = [x for x in read(path)['ideas'].values() if x.get('status') == 'proposed']
    return sorted(ideas, key=lambda x: (VALUE_RANK.get(x.get('value', '').casefold(), 3), x.get('first_seen', '')))


def _short(title, limit=60):
    title = str(title or '')
    return title if len(title) <= limit else title[:limit - 1] + '…'


def card(ideas, limit=5):
    """Owner message and buttons for ideas waiting for a decision."""
    shown = ideas[:limit]
    lines = ['💡 Идеи тестировщика — решите одной кнопкой:']
    for number, idea in enumerate(shown, 1):
        lines.append(f"\n{number}. {idea['title']} ({idea['id']}"
                     + (f", ценность {idea['value']}" if idea.get('value') else '') + ')')
        if idea.get('why'):
            lines.append('Что мешает: ' + idea['why'])
        if idea.get('how'):
            lines.append('Как: ' + idea['how'])
    if len(ideas) > limit:
        lines.append(f"\n…и ещё {len(ideas) - limit} — откройте «☰ Ещё → 💡 Идеи тестировщика».")
    lines.append('\n«✅ Берём» — разработчик сделает в отдельной ветке, в рабочий бот попадёт только после '
                 'проверки тестировщиком и вашего выпуска. «🚫 Не надо» — идея больше не предлагается.')
    keyboard = [[{'text': f"✅ Берём {idea['id']}"}, {'text': f"🚫 Не надо {idea['id']}"}] for idea in shown]
    keyboard.append([{'text': '⬅️ Главное меню'}])
    return '\n'.join(lines), {'keyboard': keyboard, 'resize_keyboard': True, 'one_time_keyboard': True}


def _update(ident, allowed, path=None, **fields):
    state = read(path)
    record = state['ideas'].get(ident)
    if not record or record.get('status') not in allowed:
        return None
    record.update(fields)
    save(state, path)
    return dict(record)


def decide(ident, take, path=None, now=None):
    return _update(ident, {'proposed'}, path, status='taken' if take else 'declined',
                   decided_at=(now or utc_now()).isoformat(timespec='seconds'))


def start(ident, path=None):
    """Claim a taken idea for the developer exactly once."""
    return _update(ident, {'taken'}, path, status='running', started_at=utc_now().isoformat(timespec='seconds'))


def finish(ident, ok, verification=None, path=None):
    return _update(ident, {'running'}, path, status='done' if ok else 'failed',
                   finished_at=utc_now().isoformat(timespec='seconds'),
                   verification={k: (verification or {}).get(k) for k in ('ok', 'status', 'problems')})


def developer_task(record):
    """The idea as a handoff task: same rules, branch and GitHub verification."""
    body = f"""Владелец взял идею AI-тестировщика кнопкой «✅ Берём».

Идея: {record['title']}
Что мешало менеджеру: {record.get('why') or 'не указано'}
Как предложил тестировщик: {record.get('how') or 'не указано'}
Ценность: {record.get('value') or 'не указана'}; миссия исследователя: {record.get('mission') or '—'}

Что сделать:
1. Найди в коде место сценария, о котором идея; если бот уже умеет это — ничего не меняй,
   status: done и объясни в отчёте, как это сделать сейчас (это тоже результат).
2. Минимальное изменение, без новых хозяйственных записей без предпросмотра и кнопки.
3. Человеческий маршрут на стенде (telegram-bridge/test_human_*.py, HumanJourneyCase): шаги
   менеджера и число действий до и после; плюс затронутые тесты и quality_gate.py --run.
4. Запись в telegram-bridge/docs/architecture/CHANGELOG.md и строка в QA_IDEAS.md.
Выпуск — отдельным заданием после проверки тестировщиком."""
    return {'id': record['id'], 'kind': 'code', 'priority': 'P2', 'title': record['title'],
            'summary': record['title'], 'ref': 'qa-ideas', 'path': 'qa_ideas_state.json',
            'sha256': hashlib.sha256(body.encode()).hexdigest(), 'body': body}


def weekly_text(path=None, now=None, days=7):
    """Friday review: every idea of the week and what happened to it."""
    now = now or utc_now()
    since = now - dt.timedelta(days=days)
    week = []
    for record in read(path)['ideas'].values():
        try:
            if dt.datetime.fromisoformat(record.get('last_seen') or record['first_seen']) >= since:
                week.append(record)
        except (KeyError, ValueError, TypeError):
            continue
    if not week:
        return '💡 Идеи за неделю: новых предложений не было.'
    order = list(STATUS_WORDS)
    week.sort(key=lambda x: (order.index(x.get('status')) if x.get('status') in order else len(order),
                             x.get('first_seen', '')))
    counts = {}
    for record in week:
        counts[record.get('status')] = counts.get(record.get('status'), 0) + 1
    lines = [f"💡 Идеи тестировщика за неделю: {len(week)}. "
             f"Ждут решения: {counts.get('proposed', 0)}; взяты: "
             f"{sum(counts.get(s, 0) for s in ('taken', 'running', 'done', 'failed'))}; "
             f"не берём: {counts.get('declined', 0)}."]
    for record in week:
        lines.append(f"• {_short(record['title'], 90)} — {STATUS_WORDS.get(record.get('status'), record.get('status'))}")
    return '\n'.join(lines)
