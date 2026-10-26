"""Scheduled QA execution, technical handoff, and owner digest.

The autopilot never performs business writes.  It runs the isolated QA profiles,
records evidence, and may approve only findings that are explicitly technical.
"""
import datetime as dt
import json
import subprocess
from pathlib import Path

import qa_handoff


ROOT = Path(__file__).resolve().parent
AGENT = ROOT / 'docs' / 'architecture' / 'qa_agent.py'
HUMAN_POLICY = ROOT / 'docs' / 'architecture' / 'HUMAN_QA_POLICY.json'
PYTHON = '/home/kocher.av/.report-venv/bin/python'


# The explorer drives a real model step by step; it needs a longer bound.
TIMEOUTS = {'explore': 3 * 3600}


def run(profile='human', runner=subprocess.run):
    completed = runner([PYTHON, str(AGENT), 'run', '--profile', profile],
                       cwd=ROOT, capture_output=True, text=True, timeout=TIMEOUTS.get(profile, 3600))
    if completed.returncode:
        return {'ok': False, 'error': (completed.stderr or completed.stdout)[-2000:]}
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError):
        return {'ok': False, 'error': 'QA runner не вернул структурированную квитанцию'}
    return {'ok': True, **payload}


def owner_messages_allowed(path=None):
    path = HUMAN_POLICY if path is None else Path(path)
    try:
        policy = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return False
    return policy.get('owner_messages_readonly') is True


def reviewable(task):
    """AI-explorer findings are a model's judgement: the owner decides on handoff."""
    return any(str(item.get('id') or '').startswith('explore:') for item in task.get('failures') or [])


def technical(task, policy_path=None):
    """Only code/test failures are technical; external prerequisites are not."""
    if reviewable(task):
        return False
    failures = task.get('failures') or []
    # Permission to use owner messages defines an allowed evidence source.  It
    # does not turn a conversation that has not happened into a code defect.
    external_prerequisites = ('decision:', 'coverage:HUMAN-', 'infra:')
    return bool(failures) and not any(
        str(item.get('id') or '').startswith(external_prerequisites)
        for item in failures)


def approve_technical(task):
    if not task or not technical(task):
        return None
    if task.get('status') == 'approved':
        return task
    if task.get('status') != 'ready':
        return None
    return qa_handoff.decide(task['id'], True)


def defer_external(task):
    if not task or technical(task) or reviewable(task):
        return None
    return qa_handoff.defer_external(
        task['id'],
        'Нужен реальный внешний вход или бизнес-решение; это не задача изменения кода.',
    )


JOURNEYS = ROOT / 'docs' / 'architecture' / 'HUMAN_JOURNEYS.json'

# What a task is about and who acts, in the owner's words (owner request 23.10:
# «не бездушные номера, а суть вкратце»).
STATUS_WORDS = {
    'ready': 'ждёт передачи разработчику', 'approved': 'передаётся разработчику',
    'fixing': 'разработчик чинит', 'awaiting_verification': 'исправлено, тестировщик перепроверит',
    'awaiting_release': 'исправлено в ветке, ждёт проверки тестировщика и выпуска',
    'waiting_input': 'ждёт внешних данных',
}
INFRA_WORDS = {
    'infra:playwright-browser': 'на сервере не запускается браузер для browser-проверок',
    'infra:crm-snapshot': 'нет свежего снимка CRM для живых маршрутов (только чтение)',
    'infra:explore-no-receipt': 'AI-исследователь не вернул результат (модель не ответила вовремя)',
    'infra:explore-judge': 'AI-судья не оценил миссию исследователя',
}


COVERAGE_WORDS = {
    '': 'маршрут {name} ещё не автоматизирован — в плане тестировщика',
    'case-not-passed': 'маршрут {name} не прошёл на снимке CRM',
    'unverified-fixture': 'для маршрута {name} нет подтверждённого снимка CRM',
    'evidence-missing': 'для маршрута {name} нет файла снимка CRM',
    'evidence-hash-mismatch': 'снимок CRM для маршрута {name} изменился после записи',
    'dialogue-missing': 'у маршрута {name} нет записи диалога',
    'readback-missing': 'у маршрута {name} нет проверки результата чтением',
}


def planned(failure):
    """A journey not automated yet is the tester's planned work, not a wait for data."""
    ident = str(failure.get('id') or '')
    return ident.startswith('coverage:') and ':' not in ident.removeprefix('coverage:')


def _journey_titles(path=None):
    try:
        registry = json.loads(Path(path or JOURNEYS).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError):
        return {}
    return {str(item.get('id')): str(item.get('title') or '') for item in registry.get('journeys') or []}


def failure_gist(failure, titles=None):
    """One failure in plain words: the judge's title, a journey name, or a known infra gap."""
    if failure.get('title'):
        return str(failure['title'])
    ident = str(failure.get('id') or 'неизвестная проверка')
    if ident.startswith('coverage:'):
        journey, _, reason = ident.removeprefix('coverage:').partition(':')
        name = f"«{(titles or {}).get(journey) or journey}»"
        return COVERAGE_WORDS.get(reason, 'маршрут {name} не подтверждён прогоном на снимке CRM').format(name=name)
    if ident.startswith('decision:'):
        return 'нужно ваше решение: ' + ident.removeprefix('decision:')
    for prefix, words in INFRA_WORDS.items():
        if ident.startswith(prefix):
            return words
    if ident.startswith('isolation:'):
        return 'проверка попыталась обратиться к рабочим данным и была остановлена'
    return 'не прошла проверка ' + ident.rsplit('.', 1)[-1]


def task_gist(task, titles=None):
    failures = task.get('failures') or []
    words = list(dict.fromkeys(failure_gist(item, titles) for item in failures))
    more = f' (+ ещё {len(words) - 2})' if len(words) > 2 else ''
    return '; '.join(words[:2]) + more if words else 'причина не записана'


def _task_lines(tasks, titles, limit):
    lines = [f"• {task_gist(task, titles)} — {STATUS_WORDS.get(task.get('status'), task.get('status'))}"
             f" ({task.get('severity') or 'P2'}, {task['id']})" for task in tasks[:limit]]
    if len(tasks) > limit:
        lines.append(f"…и ещё {len(tasks) - limit}.")
    return lines


def digest(path=qa_handoff.PRODUCTION_STATE, now=None, journeys=None, limit=5):
    state = qa_handoff._read(path)
    titles = _journey_titles(journeys)
    today = (now or dt.datetime.now(dt.timezone.utc)).date()
    runs = [x for x in state.get('runs') or []
            if dt.datetime.fromisoformat(x['at']).date() == today]
    tasks = state.get('tasks') or []
    severity = lambda task: (str(task.get('severity') or 'P2'), task.get('created_at') or '')
    active = sorted((x for x in tasks if x.get('status') in STATUS_WORDS), key=severity)
    code = [x for x in active if x.get('status') != 'waiting_input']
    waiting = [x for x in active if x.get('status') == 'waiting_input']
    passed = sum(bool(x.get('successful')) for x in runs)
    lines = ["🧪 AI-тестировщик за сегодня",
             f"Прогонов: {len(runs)}; успешных: {passed}; с замечаниями: {len(runs) - passed}."]
    failed = {}
    for run in runs:
        if not run.get('successful'):
            failed.setdefault(run.get('profile') or 'проверка', []).extend(run.get('failures') or [])
    for profile, failures in failed.items():
        words = list(dict.fromkeys(failure_gist(item, titles) for item in failures))
        lines.append(f"• {profile}: " + ('; '.join(words[:2]) + (f' (+ ещё {len(words) - 2})' if len(words) > 2 else '')
                                         if words else 'прогон не завершился'))
    if code:
        lines += [f"\nДефекты кода ({len(code)}) — их ведут тестировщик и разработчик, от вас ничего не нужно:"]
        lines += _task_lines(code, titles, limit)
    else:
        lines.append("\nОткрытых дефектов кода нет.")
    plan = list(dict.fromkeys((titles or {}).get(str(f['id']).removeprefix('coverage:')) or str(f['id']).removeprefix('coverage:')
                              for task in waiting for f in task.get('failures') or [] if planned(f)))
    waiting = [dict(task, failures=[f for f in task.get('failures') or [] if not planned(f)]) for task in waiting]
    waiting = [task for task in waiting if task['failures']]
    if waiting:
        lines += [f"\nНе код, ждут данных или решения ({len(waiting)}):"]
        lines += _task_lines(waiting, titles, limit)
    if plan:
        lines.append("\nЕщё не автоматизированы (в плане тестировщика): " + ', '.join(f'«{name}»' for name in plan) + '.')
    return "\n".join(lines)
