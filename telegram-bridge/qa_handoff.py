"""Human-approved handoff from QA findings to the existing developer agent."""
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


PRODUCTION_STATE = Path(__file__).resolve().parent / 'docs' / 'architecture' / 'qa-agent-state.json'
STATE = PRODUCTION_STATE
QA_SERVICE_USER = os.environ.get('QA_SERVICE_USER', 'smartbild-projects')


def acl_spec():
    """Both writers once: setfacl rejects a duplicate entry (QA 25.10, service user = owner)."""
    users = dict.fromkeys([QA_SERVICE_USER, 'kocher.av'])
    return ','.join(f'u:{user}:rw' for user in users) + ',m:rw'


def _grant_shared_access(path):
    # Shared QA files inherit a default ACL.  The confined service account is
    # allowed to write data but intentionally cannot rewrite filesystem ACLs.
    completed = subprocess.run(
        ['setfacl', '-m', acl_spec(), str(path)],
        capture_output=True, text=True,
    )
    if completed.returncode:
        raise OSError('Не удалось выдать доступ к QA-реестру: ' + completed.stderr.strip())


def _is_production_state(path):
    return Path(path).resolve() == PRODUCTION_STATE.resolve()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _read(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'version': 1, 'runs': [], 'tasks': []}
    if not isinstance(value, dict) or not isinstance(value.get('tasks'), list):
        raise ValueError('Повреждён реестр QA-задач')
    return value


def _save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.qa-handoff-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush(); os.fsync(stream.fileno())
        os.chmod(temporary, 0o660)
        if _is_production_state(path):
            _grant_shared_access(temporary)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _mutate(path, change):
    path = Path(path); lock = Path(str(path) + '.lock'); lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, 'a', encoding='utf-8') as stream:
        if os.fstat(stream.fileno()).st_uid == os.geteuid():
            os.chmod(lock, 0o660)
        if _is_production_state(path):
            _grant_shared_access(lock)
        fcntl.flock(stream, fcntl.LOCK_EX)
        state = _read(path); result = change(state); _save(path, state); return result


def ready(path=None, include_notified=True):
    path = STATE if path is None else path
    tasks = [item for item in _read(path)['tasks'] if item.get('status') == 'ready']
    if not include_notified:
        tasks = [item for item in tasks if not item.get('owner_notified_at')]
    return sorted(tasks, key=lambda item: (item.get('severity') != 'P1', item.get('created_at') or ''))


def summarize(task):
    failures = task.get('failures') or []
    names = [str(item.get('id') or '').removeprefix('coverage:') +
             (f" — {item['title']}" if item.get('title') else '') for item in failures[:4]]
    more = len(failures) - len(names)
    scope = ', '.join(names) + (f' и ещё {more}' if more > 0 else '')
    return (f"🧪 QA нашёл проблему [{task['id']}]\n"
            f"Приоритет: {task.get('severity', 'P2')}\n"
            f"Проверка: {task.get('profile', 'unknown')}\n"
            f"Затронуто: {scope or 'не определено'}\n"
            f"Повторов: {task.get('occurrences', 1)}\n\n"
            "Передать агенту-разработчику? Он получит полную квитанцию, добавит регрессию и вернёт отчёт. Выпуск останется отдельным этапом.")


def developer_prompt(task):
    failures = '\n'.join(f"- {x.get('status')}: {x.get('id')}" for x in task.get('failures') or [])
    return f"""Автоматически подтверждённая владельцем QA-задача SmartBild.
ID: {task['id']}; приоритет: {task.get('severity')}; профиль: {task.get('profile')}.
Квитанция: {task.get('evidence')}.
Наблюдения:
{failures}

Сначала воспроизведи проблему через тот же человеческий маршрут. Исправь общий механизм, добавь регрессию на границе модулей и проверь соседние входы. Не ослабляй тесты. Не повторяй уже успешные финансовые, CRM, архивные или доставочные эффекты. Выполни затронутые тесты и полный quality_gate; browser runner при изменении пульта. Обнови карточку QA-2026-10-14 и CHANGELOG. Если требуется бизнес-решение, задай владельцу один конкретный вопрос через существующий decision_channel; технические решения принимай самостоятельно. Не выполняй хозяйственные записи ради проверки без отдельного разрешения.
"""


def handoff_task(task):
    """The QA repair as a handoff task: branch handoff/<id>, report in handoff/outbox."""
    body = developer_prompt(task) + """
Маршрут (решение владельца 25.10): исправление — только в ветке handoff/{id}; в работающий бот
ничего не копируй и службу не перезагружай. Тестировщик проверит ветку, выпуск — кнопкой владельца.
Если QA-реестр и стенд не воспроизводят дефект из служебного клона — status: blocked с причиной.""".replace('{id}', task['id'])
    names = [str(item.get('title') or item.get('id') or '') for item in task.get('failures') or []]
    title = 'Исправить по QA: ' + ('; '.join(names[:2]) or task['id'])
    return {'id': task['id'], 'kind': 'code', 'priority': task.get('severity') or 'P2', 'title': title,
            'summary': title, 'ref': 'qa-agent', 'path': 'qa-agent-state.json',
            'sha256': hashlib.sha256(body.encode()).hexdigest(), 'body': body}


def mark_notified(task_id, message_id, path=None):
    path = STATE if path is None else path
    def change(state):
        task = next((item for item in state['tasks'] if item.get('id') == task_id), None)
        if not task or task.get('status') != 'ready': return False
        task.update(owner_notified_at=now(), owner_message_id=message_id); return True
    return _mutate(path, change)


def decide(task_id, approved, path=None):
    path = STATE if path is None else path
    def change(state):
        task = next((item for item in state['tasks'] if item.get('id') == task_id), None)
        if not task or task.get('status') != 'ready': return None
        task['owner_decided_at'] = now()
        task['status'] = 'approved' if approved else 'dismissed'
        return dict(task)
    return _mutate(path, change)


def claim(task_id, path=None):
    path = STATE if path is None else path
    def change(state):
        task = next((item for item in state['tasks'] if item.get('id') == task_id), None)
        if not task or task.get('status') != 'approved': return None
        task.update(status='fixing', developer_started_at=now()); return dict(task)
    return _mutate(path, change)


def finish(task_id, report, ok, path=None, status=None):
    path = STATE if path is None else path
    def change(state):
        task = next((item for item in state['tasks'] if item.get('id') == task_id), None)
        if not task or task.get('status') != 'fixing': return None
        task.update(status=status or ('awaiting_verification' if ok else 'approved'), developer_finished_at=now(),
                    developer_report=str(report or '')[-20000:]); return dict(task)
    return _mutate(path, change)


def defer_external(task_id, reason, path=None):
    """Remove a non-code prerequisite from the developer queue without losing it."""
    path = STATE if path is None else path
    def change(state):
        task = next((item for item in state['tasks'] if item.get('id') == task_id), None)
        if not task or task.get('status') not in {'ready', 'approved', 'awaiting_verification'}:
            return None
        task.update(status='waiting_input', waiting_since=now(), waiting_reason=str(reason))
        return dict(task)
    return _mutate(path, change)


def resume_waiting(task_id, reason, path=None):
    """Resume the same task after its external prerequisite is satisfied."""
    path = STATE if path is None else path
    def change(state):
        task = next((item for item in state['tasks'] if item.get('id') == task_id), None)
        if not task or task.get('status') != 'waiting_input':
            return None
        task.update(status='ready', resumed_at=now(), resume_reason=str(reason),
                    waiting_reason=None)
        return dict(task)
    return _mutate(path, change)
