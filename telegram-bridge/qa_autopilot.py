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


def run(profile='human', runner=subprocess.run):
    completed = runner([PYTHON, str(AGENT), 'run', '--profile', profile],
                       cwd=ROOT, capture_output=True, text=True, timeout=3600)
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


def technical(task, policy_path=None):
    """Only code/test failures are technical; external prerequisites are not."""
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
    if not task or technical(task):
        return None
    return qa_handoff.defer_external(
        task['id'],
        'Нужен реальный внешний вход или бизнес-решение; это не задача изменения кода.',
    )


def digest(path=qa_handoff.PRODUCTION_STATE, now=None):
    state = qa_handoff._read(path)
    today = (now or dt.datetime.now(dt.timezone.utc)).date()
    runs = [x for x in state.get('runs') or []
            if dt.datetime.fromisoformat(x['at']).date() == today]
    tasks = state.get('tasks') or []
    active = [x for x in tasks if x.get('status') in
              {'ready', 'approved', 'fixing', 'awaiting_verification', 'waiting_input'}]
    passed = sum(bool(x.get('successful')) for x in runs)
    failed = len(runs) - passed
    return (f"🧪 AI-тестировщик за сегодня\n"
            f"Прогонов: {len(runs)}; успешных: {passed}; с дефектами: {failed}.\n"
            f"Активных QA-задач: {len(active)}"
            + ("\n" + "\n".join(f"• {x['id']} — {x.get('status')} ({x.get('severity')})" for x in active[:5])
               if active else "\nОткрытых технических дефектов нет."))
