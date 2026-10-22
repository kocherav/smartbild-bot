"""SmartBild QA orchestrator: evidence in, deduplicated developer tasks out.

The agent is intentionally separated from business handlers.  It can run offline
acceptance commands and inspect their receipts, but it never writes to CRM,
Telegram, email, archives, finance ledgers, or production queues.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT.parent.parent
PYTHON = os.environ.get('QA_PYTHON', '/home/kocher.av/.report-venv/bin/python')
DEFAULT_STATE = ROOT / 'qa-agent-state.json'
DEFAULT_EVIDENCE = ROOT / 'qa-agent-evidence'
FULL_GATE = [PYTHON, str(ROOT / 'quality_gate.py'), '--run']
BROWSER_GATE = ['/usr/bin/python3', '/home/kocher.av/hogart-scraper/dashboard/tests/run_browser_checks.py']
# The isolated runner copies only sources; then the registry is read in place.
HUMAN_JOURNEYS = next((path for path in (
    ROOT / 'HUMAN_JOURNEYS.json',
    Path(os.environ.get('SMARTBILD_HOME', '/home/kocher.av')) / 'telegram-bridge/docs/architecture/HUMAN_JOURNEYS.json',
) if path.exists()), ROOT / 'HUMAN_JOURNEYS.json')
HUMAN_FIXTURES = ROOT / 'human-fixtures'
# A person operating the real bridge: stand suites plus the real-CRM snapshot suite.
HUMAN_MODULES = ['test_human_operator_journey', 'test_human_journeys', 'test_human_journeys_edge',
                 'test_human_journeys_documents', 'test_human_phrasings', 'test_human_recovery',
                 'human_live_journeys']
QA_SERVICE_USER = os.environ.get('QA_SERVICE_USER', 'smartbild-projects')

CRITICAL_WORDS = {
    'financial', 'finance', 'payment', 'bank', 'allocation', 'settlement',
    'delivery', 'archive', 'auth', 'role', 'safe_reload', 'effect_runner',
}


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load_json(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'),
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except FileNotFoundError:
        return default()
    if not isinstance(value, dict):
        raise ValueError(f'Некорректная структура JSON: {path}')
    return value


def atomic_save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    descriptor, temporary = tempfile.mkstemp(prefix='.qa-agent-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o660)
        if path.resolve() == DEFAULT_STATE.resolve():
            # os.access() only describes the current writer.  The previous
            # guard silently removed the *other* writer on every atomic replace.
            completed = subprocess.run(
                ['setfacl', '-m', f'u:{QA_SERVICE_USER}:rw,u:kocher.av:rw,m:rw', temporary],
                capture_output=True, text=True,
            )
            if completed.returncode:
                raise OSError('Не удалось выдать доступ к QA-реестру: ' + completed.stderr.strip())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def report_failures(report):
    failures = []
    for case in report.get('cases') or []:
        if case.get('status') in {'failed', 'error', 'skipped', 'missing', 'blocked'}:
            failure = {'id': str(case.get('id') or 'unknown'), 'status': case.get('status')}
            # Explorer findings carry the judge's own wording and priority.
            failure.update({key: case[key] for key in ('title', 'severity') if case.get(key)})
            failures.append(failure)
    for event in report.get('blocked_events') or []:
        failures.append({'id': 'isolation:' + str(event.get('event') or 'unknown'), 'status': 'blocked'})
    if not failures and not report.get('successful', False):
        failures.append({'id': 'runner:incomplete', 'status': 'failed'})
    return failures


def _coverage_failure(journey_id, reason=None):
    suffix = ':' + reason if reason else ''
    return {'id': 'coverage:' + journey_id + suffix, 'status': 'missing'}


def human_coverage_failures(path=HUMAN_JOURNEYS, report=None):
    """Validate executable human evidence, never a declaration alone.

    A journey counts only when the current receipt contains its passed case with
    a human/bot transcript and an explicit successful observation, and the
    read-only fixture named by the registry still matches its recorded digest.
    """
    registry = load_json(path, dict)
    report = report or {}
    cases = {str(item.get('id')): item for item in report.get('cases') or []}
    registry_root = Path(path).resolve().parent
    failures = []
    for item in registry.get('journeys') or []:
        journey_id = item['id']
        if not item.get('automated'):
            failures.append(_coverage_failure(journey_id))
            continue
        provenance = shared_provenance(path, item)
        required = {'source', 'captured_at', 'evidence', 'sha256'}
        if provenance.get('source') != 'crm-readonly' or not required.issubset(provenance):
            failures.append(_coverage_failure(journey_id, 'unverified-fixture'))
            continue
        evidence = Path(provenance['evidence'])
        evidence = evidence if evidence.is_absolute() else registry_root / evidence
        try:
            payload = evidence.read_bytes()
        except (OSError, ValueError):
            failures.append(_coverage_failure(journey_id, 'evidence-missing'))
            continue
        if hashlib.sha256(payload).hexdigest() != provenance['sha256']:
            failures.append(_coverage_failure(journey_id, 'evidence-hash-mismatch'))
            continue
        case_ids = [str(x) for x in item.get('test_cases') or [item.get('test_case') or '']]
        for case_id in case_ids:
            case = cases.get(case_id)
            if not case or case.get('status') != 'passed':
                failures.append(_coverage_failure(journey_id, 'case-not-passed'))
                break
            transcript = case.get('transcript') or []
            actors = {event.get('actor') for event in transcript}
            if not {'tester', 'bot'}.issubset(actors):
                failures.append(_coverage_failure(journey_id, 'dialogue-missing'))
                break
            observations = case.get('observations') or []
            if not observations or any(x.get('verdict') != 'passed' for x in observations):
                failures.append(_coverage_failure(journey_id, 'readback-missing'))
                break
    return failures


EXTERNAL_PREFIXES = ('decision:', 'coverage:HUMAN-', 'infra:')


def is_external(failure):
    """Owner decisions, missing real-data evidence and infrastructure are not code work."""
    return str(failure.get('id') or '').startswith(EXTERNAL_PREFIXES)


def task_kind(task):
    failures = task.get('failures') or []
    return 'external' if failures and all(is_external(f) for f in failures) else 'technical'


def shared_provenance(registry_path, journey):
    import sys
    sys.path.insert(0, str(BRIDGE))
    import human_fixtures
    return human_fixtures.current_provenance(registry_path, journey)


def severity(failures):
    stated = sorted(item['severity'] for item in failures if item.get('severity') in ('P1', 'P2', 'P3'))
    if stated:
        return stated[0]
    if any(item['status'] == 'missing' for item in failures):
        return 'P1'
    joined = ' '.join(item['id'].casefold() for item in failures)
    return 'P1' if any(word in joined for word in CRITICAL_WORDS) else 'P2'


def fingerprint(profile, failures):
    identities = sorted(f"{item['status']}:{item['id']}" for item in failures)
    return hashlib.sha256((profile + '\n' + '\n'.join(identities)).encode()).hexdigest()[:20]


def developer_prompt(task):
    failed = '\n'.join(f"- {item['status']}: {item['id']}" for item in task['failures'])
    return f"""Задача разработчику SmartBild от автономного QA-агента

ID: {task['id']}
Приоритет: {task['severity']}
Профиль: {task['profile']}
Квитанция: {task['evidence']}
Протокол человеческого диалога: {task.get('protocol') or 'не сформирован'}

Наблюдаемый дефект:
{failed}

Обязательный порядок исправления:
1. Воспроизвести сбой на той же границе модулей и определить нарушенный бизнес-инвариант.
2. Установить корневую причину и проверить весь класс похожих входов, ролей, повторов и частичных состояний.
3. Добавить регрессию до исправления; не ослаблять существующие проверки и фикстуры.
4. Сохранить успешные внешние этапы: финансовые записи, отправки и архив не повторять из-за последующего сбоя.
5. Проверить отмену, устаревший ввод, конкуренцию, перезапуск и безопасное продолжение, где применимо.
6. Выполнить затронутые тесты, затем полный quality_gate; browser runner обязателен при изменении пульта.
7. Обновить карточку QA-2026-10-14 и CHANGELOG, разделив: реализовано, проверено изолированно, выпущено, подтверждено в работающей системе.

Запрещено автоматически выполнять хозяйственные записи или рассылки ради проверки. Живые проверки по умолчанию только читают данные. Выпуск и safe_reload выполняются отдельным этапом после действующей квитанции допуска.
"""


class Registry:
    def __init__(self, path=DEFAULT_STATE):
        self.path = Path(path)

    def read(self):
        return load_json(self.path, lambda: {'version': 1, 'runs': [], 'tasks': []})

    def record(self, profile, evidence, report, protocol=None):
        """Store a run; technical defects and external prerequisites become separate tasks.

        A missing CRM snapshot or an owner decision must never hold back a real
        code defect found in the same run, and must never be sent to a developer.
        """
        run, tasks = self.record_all(profile, evidence, report, protocol)
        return run, (tasks[0] if tasks else None)

    def record_all(self, profile, evidence, report, protocol=None):
        state = self.read()
        failures = report_failures(report)
        run = {'id': 'RUN-' + hashlib.sha256((utc_now() + str(evidence)).encode()).hexdigest()[:12],
               'at': utc_now(), 'profile': profile, 'evidence': str(evidence),
               'successful': not failures, 'tests': report.get('tests'), 'failures': failures}
        state['runs'].append(run)
        groups = {'technical': [f for f in failures if not is_external(f)],
                  'external': [f for f in failures if is_external(f)]}
        tasks = []
        for kind, group in groups.items():
            if not group:
                # A clean group closes only this profile's tasks of the same kind
                # that were waiting for exactly this verification.
                for candidate in state['tasks']:
                    if (candidate.get('profile') == profile and task_kind(candidate) == kind and
                            candidate.get('status') in {'awaiting_verification', 'waiting_input'}):
                        candidate.update(status='closed', verified_at=run['at'],
                                         verification_run=run['id'], verification_evidence=str(evidence))
                continue
            digest = fingerprint(profile, group)
            task = next((item for item in state['tasks'] if item['fingerprint'] == digest and
                         item['status'] in {'ready', 'approved', 'dispatched', 'fixing',
                                            'awaiting_verification', 'waiting_input'}), None)
            if task:
                task['occurrences'] += 1
                task['last_seen_at'] = run['at']
                task['evidence'] = str(evidence)
                if protocol: task['protocol'] = str(protocol)
                if kind == 'external':
                    task['status'] = 'waiting_input'
                    task.pop('developer_assignment', None)
                # A developer result is never accepted on its own.  The same
                # failing acceptance route returns the task to the repair queue.
                if task['status'] == 'awaiting_verification':
                    task['status'] = 'ready'
                    task['verification_failures'] = int(task.get('verification_failures') or 0) + 1
                    task['last_verification_run'] = run['id']
            else:
                task = {'id': 'QA-' + digest.upper(), 'fingerprint': digest,
                        'status': 'waiting_input' if kind == 'external' else 'ready',
                        'severity': severity(group), 'profile': profile, 'failures': group,
                        'evidence': str(evidence), 'created_at': run['at'], 'last_seen_at': run['at'],
                        'occurrences': 1, 'protocol': str(protocol) if protocol else None}
                state['tasks'].append(task)
            tasks.append(task)
        atomic_save(self.path, state)
        return run, tasks

    def task(self, task_id):
        return next((item for item in self.read()['tasks'] if item['id'] == task_id), None)

    def dispatch(self, task_id, command, runner=subprocess.run):
        if not command:
            raise ValueError('Не задана команда агента-разработчика')
        state = self.read()
        task = next((item for item in state['tasks'] if item['id'] == task_id), None)
        if not task:
            raise ValueError('Задача не найдена')
        if task['status'] not in {'ready', 'dispatched'}:
            raise ValueError('Задача уже передана или закрыта')
        task['status'] = 'dispatched'
        task['dispatched_at'] = utc_now()
        atomic_save(self.path, state)
        completed = runner(command, input=developer_prompt(task), capture_output=True, text=True)
        state = self.read()
        task = next(item for item in state['tasks'] if item['id'] == task_id)
        task['developer_returncode'] = completed.returncode
        task['developer_report'] = (completed.stdout or '')[-20000:]
        task['developer_error'] = (completed.stderr or '')[-5000:]
        task['status'] = 'awaiting_verification' if completed.returncode == 0 else 'ready'
        task['developer_finished_at'] = utc_now()
        atomic_save(self.path, state)
        return task


def write_human_protocol(report, target):
    target = Path(target)
    lines = ['# Протокол human-QA', '', f'Квитанция сформирована: {report.get("ran_at") or "не указано"}', '']
    sequence = 0
    for case in report.get('cases') or []:
        if not case.get('transcript') and not case.get('observations'):
            continue
        lines += [f"## {case.get('id')}", '', f"Статус: `{case.get('status')}`", '', '### Диалог', '']
        for event in case.get('transcript') or []:
            sequence += 1
            actor = 'Тестировщик' if event.get('actor') == 'tester' else 'Бот'
            kind = 'нажал кнопку' if event.get('kind') == 'button' else 'сказал'
            lines += [f"{sequence}. **{actor} {kind}:**", '', '   ' + str(event.get('text') or '').replace('\n', '\n   '), '']
        lines += ['### Проверка результата', '']
        for item in case.get('observations') or []:
            lines += [f"- Ожидалось: {item.get('expected')}", f"- Получено: {item.get('actual')}",
                      f"- Вердикт: `{item.get('verdict')}`", '']
    if sequence == 0:
        lines += ['Диалоговых свидетельств в этой квитанции нет.', '']
    target.write_text('\n'.join(lines), encoding='utf-8')
    return target


def inspect_receipt(profile, receipt, registry):
    report = load_json(receipt, dict)
    protocol = (write_human_protocol(report, Path(receipt).with_name('conversation-protocol.md'))
                if profile in ('human', 'explore') else None)
    run, tasks = registry.record_all(profile, receipt, report, protocol=protocol)
    if tasks:
        state = registry.read()
        for task in tasks:
            if task_kind(task) == 'external':
                continue
            suffix = '' if task is tasks[0] else '-' + task_kind(task)
            assignment = Path(receipt).with_name(f'developer-assignment{suffix}.md')
            assignment.write_text(developer_prompt(task), encoding='utf-8')
            task['developer_assignment'] = str(assignment)
            stored = next(item for item in state['tasks'] if item['id'] == task['id'])
            stored['developer_assignment'] = str(assignment)
        atomic_save(registry.path, state)
    task = tasks[0] if tasks else None
    return {'run': run, 'task': task, 'tasks': tasks,
            'developer_prompt': developer_prompt(task) if task and task_kind(task) == 'technical' else None}


def run_profile(profile, evidence_root=DEFAULT_EVIDENCE, runner=subprocess.run):
    if profile == 'full':
        command = FULL_GATE
    elif profile == 'browser':
        command = BROWSER_GATE
    elif profile == 'explore':
        command = [PYTHON, str(BRIDGE / 'human_qa_explorer.py'), '--output']
    else:
        command = [PYTHON, str(ROOT / 'offline_tests.py'), *HUMAN_MODULES, '--output']
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    # Human and full profiles are intentionally launched in the same scheduler
    # tick.  A profile/nonce suffix prevents one run from stealing the other's
    # evidence directory and losing a daily execution after it was claimed.
    folder = Path(evidence_root) / f'{stamp}-{profile}-{uuid.uuid4().hex[:8]}'
    folder.mkdir(parents=True, exist_ok=False)
    if profile in ('human', 'explore'):
        command = command + [str(folder)]
    elif profile == 'browser':
        command = command + ['--evidence', str(folder / 'browser-audit.json')]
    environment = {**os.environ, 'QA_HUMAN_REGISTRY': str(HUMAN_JOURNEYS)}
    completed = runner(command, cwd=BRIDGE if profile == 'explore' else ROOT, capture_output=True,
                       text=True, env=environment)
    execution = {'profile': profile, 'command': command, 'returncode': completed.returncode,
                 'stdout': completed.stdout[-20000:], 'stderr': completed.stderr[-20000:]}
    atomic_save(folder / 'execution.json', execution)
    if profile == 'full':
        source = ROOT / 'audit-20261012' / 'LAST_TEST_RUN.json'
        if source.exists():
            report = load_json(source, dict)
        else:
            report = {'successful': False, 'cases': [{'id': 'quality_gate:no_receipt', 'status': 'error'}]}
    elif profile == 'browser':
        output = (completed.stdout or '') + '\n' + (completed.stderr or '')
        if completed.returncode == 0:
            cases = []
        elif "Executable doesn't exist" in output and 'ms-playwright' in output:
            cases = [{'id': 'infra:playwright-browser', 'status': 'blocked'}]
        else:
            cases = [{'id': 'dashboard:browser_runner', 'status': 'failed'}]
        report = {'successful': completed.returncode == 0, 'tests': None, 'cases': cases}
    elif profile == 'explore':
        report_path = folder / 'LAST_TEST_RUN.json'
        report = load_json(report_path, dict) if report_path.exists() else {
            'successful': False, 'cases': [{'id': 'infra:explore-no-receipt', 'status': 'blocked'}]}
    else:
        report_path = folder / 'LAST_TEST_RUN.json'
        report = load_json(report_path, dict) if report_path.exists() else {
            'successful': False, 'cases': [{'id': 'human:no_receipt', 'status': 'error'}]}
        snapshot_problem = live_snapshot_problem()
        if snapshot_problem:
            # Real-data journeys cannot run without a snapshot.  That is an
            # infrastructure prerequisite for the owner, not a code defect.
            for case in report.get('cases') or []:
                if str(case.get('id', '')).startswith('human_live_journeys.') and case.get('status') != 'passed':
                    case['id'] = 'infra:crm-snapshot:' + case['id'].rsplit('.', 1)[-1]
                    case['status'] = 'blocked'
                    case['reason'] = snapshot_problem
        gaps = human_coverage_failures(report=report)
        if gaps:
            report['successful'] = False
            report.setdefault('cases', []).extend(gaps)
    atomic_save(folder / 'receipt.json', report)
    return folder / 'receipt.json'


def live_snapshot_problem(registry_path=HUMAN_JOURNEYS):
    import sys
    sys.path.insert(0, str(BRIDGE))
    import human_fixtures
    return human_fixtures.verified_snapshot(registry_path)[1]


def capture_fixture(deal_ids, registry_path=HUMAN_JOURNEYS, folder=HUMAN_FIXTURES):
    """Read-only snapshot of real deals; every automated journey then points at it."""
    import sys
    sys.path.insert(0, str(BRIDGE))
    import human_fixtures
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    target = Path(folder) / f'crm-{stamp}.json'
    snapshot, digest = human_fixtures.capture(deal_ids, target)
    human_fixtures.register(registry_path, target, digest, snapshot['captured_at'])
    return {'snapshot': str(target), 'sha256': digest, 'deals': [d['deal']['id'] for d in snapshot['deals']],
            'problems': snapshot['problems']}


def main():
    parser = argparse.ArgumentParser(description='SmartBild QA agent')
    parser.add_argument('--state', type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest='action', required=True)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('--profile', choices=('full', 'browser', 'human', 'explore'), default='human')
    inspect_parser = sub.add_parser('inspect')
    inspect_parser.add_argument('receipt', type=Path)
    inspect_parser.add_argument('--profile', default='full')
    prompt_parser = sub.add_parser('prompt')
    prompt_parser.add_argument('task_id')
    dispatch_parser = sub.add_parser('dispatch')
    dispatch_parser.add_argument('task_id')
    dispatch_parser.add_argument('command', nargs=argparse.REMAINDER)
    capture_parser = sub.add_parser('capture', help='снять read-only снимок CRM для human-маршрутов')
    capture_parser.add_argument('--deal', action='append', required=True, help='номер сделки (можно несколько)')
    sub.add_parser('list')
    args = parser.parse_args()
    registry = Registry(args.state)
    if args.action == 'run':
        receipt = run_profile(args.profile)
        result = inspect_receipt(args.profile, receipt, registry)
    elif args.action == 'capture':
        result = capture_fixture(args.deal)
    elif args.action == 'inspect':
        result = inspect_receipt(args.profile, args.receipt, registry)
    elif args.action == 'prompt':
        task = registry.task(args.task_id)
        if not task:
            raise SystemExit('Задача не найдена')
        print(developer_prompt(task))
        return
    elif args.action == 'dispatch':
        command = args.command[1:] if args.command[:1] == ['--'] else args.command
        result = registry.dispatch(args.task_id, command)
    else:
        result = registry.read()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
