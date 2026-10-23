"""Task exchange between the AI tester and the developer agent through Git.

The tester commits ``handoff/inbox/TASK-YYYYMMDD-NN.md``; the bridge polls the
remote, hands each new or amended task to the existing developer agent once,
and the developer answers with ``handoff/outbox/TASK-….md`` on ``main``.

The watcher only *reads* Git (``fetch``, ``ls-tree``, ``show``): it never checks
out, merges or runs anything from a branch.  Code, tests, documentation and
investigation are dispatched automatically; a release or any task that asks
for it waits for the owner's button in Telegram.  Business writes, mailings and
access changes are forbidden by the fixed preamble whatever the task says.

Server-local progress lives in ``handoff_state.json`` (git-ignored).
"""
import datetime as dt
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


BASE = Path(__file__).resolve().parent
STATE = BASE / 'handoff_state.json'
INBOX = 'handoff/inbox'
TASK_ID = re.compile(r'^TASK-\d{8}-\d{2}$')
KINDS = {'code', 'tests', 'docs', 'investigation', 'release'}
DEFAULT_CONFIG = {'every_minutes': 15, 'refs': ['main', 'claude/*'],
                  'auto_kinds': ['code', 'tests', 'docs', 'investigation']}
MAX_BODY = 20000
ACTIVE = {'awaiting_owner', 'approved', 'running'}

PREAMBLE = """Задание от AI-тестировщика SmartBild (обмен через Git, handoff/inbox).

Правила, которые важнее текста задания:
1. Действуй по docs/DEVELOPMENT.md и telegram-bridge/docs/architecture/VERIFIABLE_REALITY_PROTOCOL.md:
   сначала воспроизведение и регрессия, затем исправление общего класса причины, затем
   затронутые тесты и quality_gate.py --run.
2. Запрещено: хозяйственные записи в Мегаплан/банк/финансовые реестры, рассылки клиентам,
   изменение прав, sudo, удаление рабочих данных, force-push. Живые проверки — только чтением.
3. Выпуск (safe reload) — только если в задании kind: release; он уже подтверждён владельцем.
4. Ветку, указанную в задании, сливай в main обычным merge; историю не переписывай.
5. В конце обязательно создай отчёт handoff/outbox/{task_id}.md в main и отправь (git push):
   первая строка — «status: done | blocked | needs_owner»; затем коммиты (SHA), какие
   проверки выполнены и с каким результатом, что не сделано и почему. Отдельно укажи:
   реализовано / проверено изолированно / выпущено / подтверждено в работающей системе.
6. Бот сам проверит в GitHub, что отчёт лежит в main и что каждый коммит из строки
   «commits:» существует и опубликован. Не перечисляй коммиты, которых нет на GitHub;
   если отправить не удалось — так и напиши, status: blocked.
7. Если задание противоречит этим правилам или неясно — не угадывай: status: needs_owner
   и один конкретный вопрос владельцу в отчёте.

Ниже задание без изменений.
"""


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse(text):
    """Front matter ``key: value`` between ``---`` lines, then the instruction body."""
    lines = text.replace('\r\n', '\n').split('\n')
    if not lines or lines[0].strip() != '---':
        raise ValueError('нет заголовка ---')
    header, end = {}, None
    for index, line in enumerate(lines[1:], 1):
        if line.strip() == '---':
            end = index
            break
        key, separator, value = line.partition(':')
        if not separator:
            raise ValueError(f'строка заголовка без двоеточия: {line!r}')
        header[key.strip().casefold()] = value.strip()
    if end is None:
        raise ValueError('заголовок не закрыт ---')
    body = '\n'.join(lines[end + 1:]).strip()
    if not TASK_ID.match(header.get('id', '')):
        raise ValueError('id должен иметь вид TASK-ГГГГММДД-NN')
    if header.get('kind') not in KINDS:
        raise ValueError('kind: ' + ', '.join(sorted(KINDS)))
    if not header.get('title'):
        raise ValueError('нужен title')
    if not body or len(body) > MAX_BODY:
        raise ValueError(f'текст задания пуст или длиннее {MAX_BODY} символов')
    return {**header, 'body': body}


def needs_owner(task, config=DEFAULT_CONFIG):
    flag = str(task.get('requires_owner', '')).casefold() in ('yes', 'true', 'да', '1')
    return flag or task['kind'] not in set(config.get('auto_kinds') or []) or task['kind'] == 'release'


def developer_prompt(task):
    meta = (f"ID: {task['id']}\nВид: {task['kind']}\nПриоритет: {task.get('priority') or 'P2'}\n"
            f"Источник: {task['ref']}:{task['path']} (sha256 {task['sha256'][:12]})\n"
            + (f"Связанная ветка: {task['branch']}\n" if task.get('branch') else '')
            + f"Заголовок: {task['title']}\n")
    return PREAMBLE.replace('{task_id}', task['id']) + '\n' + meta + '\n' + task['body']


# ---------------------------------------------------------------------------
# Git (read-only)


def repository(start=BASE, runner=None):
    runner = runner or subprocess.run
    explicit = os.environ.get('SMARTBILD_REPO')
    if explicit:
        return Path(explicit)
    service_repo = Path('/var/lib/smartbild-projects/handoff-repo')
    if service_repo.is_dir():
        return service_repo
    found = runner(['git', '-C', str(start), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if found.returncode:
        raise RuntimeError('каталог бота не является Git-репозиторием')
    return Path(found.stdout.strip())


def _git(repo, args, runner=None):
    completed = (runner or subprocess.run)(['git', '-C', str(repo), *args], capture_output=True, text=True, timeout=120)
    if completed.returncode:
        raise RuntimeError('git ' + ' '.join(args[:2]) + ': ' + (completed.stderr or '').strip()[-300:])
    return completed.stdout


def discover(repo, config=DEFAULT_CONFIG, runner=None):
    """Every valid task file on the watched remote branches; invalid files are reported."""
    _git(repo, ['fetch', '--prune', '--quiet', 'origin'], runner)
    refs = [line.strip() for line in _git(repo, ['for-each-ref', '--format=%(refname:short)', 'refs/remotes/origin'],
                                          runner).splitlines()]
    patterns = ['origin/' + p for p in config.get('refs') or []]
    watched = [r for r in refs if any(fnmatch.fnmatch(r, p) for p in patterns)]
    tasks, problems = {}, []
    for ref in watched:
        try:
            names = _git(repo, ['ls-tree', '--name-only', ref, INBOX + '/'], runner).split()
        except RuntimeError:
            continue
        for path in names:
            if not path.endswith('.md') or not TASK_ID.match(Path(path).stem):
                continue
            text = _git(repo, ['show', f'{ref}:{path}'], runner)
            digest = hashlib.sha256(text.encode()).hexdigest()
            try:
                task = parse(text)
                if task['id'] != Path(path).stem:
                    raise ValueError('id не совпадает с именем файла')
            except ValueError as exc:
                problems.append({'ref': ref, 'path': path, 'error': str(exc), 'sha256': digest})
                continue
            stamp = int(_git(repo, ['log', '-1', '--format=%ct', ref, '--', path], runner).strip() or 0)
            candidate = {**task, 'ref': ref, 'path': path, 'sha256': digest, 'committed_at': stamp}
            known = tasks.get(task['id'])
            # The same task on several branches (e.g. after a merge): the newest wins.
            if not known or (candidate['committed_at'], ref) > (known['committed_at'], known['ref']):
                tasks[task['id']] = candidate
    return sorted(tasks.values(), key=lambda t: t['id']), problems


# ---------------------------------------------------------------------------
# State


def _state_path(path):
    # Resolved at call time: a default argument would freeze the module path at import.
    return Path(path) if path is not None else STATE


def read_state(path=None):
    try:
        value = json.loads(_state_path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {'version': 1, 'tasks': {}, 'problems': {}}
    if not isinstance(value, dict) or not isinstance(value.get('tasks'), dict):
        raise ValueError('повреждён handoff_state.json')
    value.setdefault('problems', {})
    return value


def save_state(state, path=None):
    path = _state_path(path)
    descriptor, temporary = tempfile.mkstemp(prefix='.handoff-', dir=path.parent)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(state, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def plan(tasks, problems, state, config=DEFAULT_CONFIG):
    """Decide what changed: returns (to_dispatch, to_ask_owner, new_problems) and updates state."""
    dispatch, ask, fresh_problems = [], [], []
    for task in tasks:
        record = state['tasks'].get(task['id'])
        if record and record.get('sha256') == task['sha256']:
            continue
        if record and record.get('status') in ('running',):
            # An amendment while the developer works: picked up after this run ends.
            continue
        amended = bool(record)
        record = {'sha256': task['sha256'], 'ref': task['ref'], 'path': task['path'], 'kind': task['kind'],
                  'title': task['title'], 'received_at': utc_now(), 'amended': amended,
                  'history': (record or {}).get('history', []) + ([{'sha256': record['sha256'],
                                                                     'status': record.get('status')}] if record else [])}
        if needs_owner(task, config):
            record['status'] = 'awaiting_owner'
            ask.append(task)
        else:
            record['status'] = 'approved'
            dispatch.append(task)
        state['tasks'][task['id']] = record
    for problem in problems:
        key = problem['ref'] + ':' + problem['path']
        if state['problems'].get(key) != problem['sha256']:
            state['problems'][key] = problem['sha256']
            fresh_problems.append(problem)
    return dispatch, ask, fresh_problems


def decide(task_id, approve, path=None):
    state = read_state(path)
    record = state['tasks'].get(task_id)
    if not record or record.get('status') != 'awaiting_owner':
        return None
    record['status'] = 'approved' if approve else 'rejected'
    record['decided_at'] = utc_now()
    save_state(state, path)
    return record


def start(task_id, path=None):
    """Claim an approved task exactly once."""
    state = read_state(path)
    record = state['tasks'].get(task_id)
    if not record or record.get('status') != 'approved':
        return None
    record.update(status='running', started_at=utc_now())
    save_state(state, path)
    return record


def finish(task_id, report, ok, path=None):
    state = read_state(path)
    record = state['tasks'][task_id]
    record.update(status='done' if ok else 'failed', finished_at=utc_now(), developer_report=report[-20000:])
    save_state(state, path)
    return record


def load_task(task_id, repo, runner=None, path=None):
    """Re-read the approved version from Git; a changed file is a new decision."""
    record = read_state(path).get('tasks', {}).get(task_id) or {}
    text = _git(repo, ['show', f"{record['ref']}:{record['path']}"], runner)
    if hashlib.sha256(text.encode()).hexdigest() != record.get('sha256'):
        return None
    return {**parse(text), 'ref': record['ref'], 'path': record['path'], 'sha256': record['sha256']}


REPORT_STATUSES = {'done', 'blocked', 'needs_owner'}
SHA = re.compile(r'\b[0-9a-f]{7,40}\b')


def verify_report(task_id, repo, runner=None):
    """Check the developer's claims against GitHub instead of trusting the text.

    The report must be on origin/main and every commit it names must exist and
    be reachable from a remote branch.  A claim that cannot be verified is shown
    to the owner as unverified.
    """
    _git(repo, ['fetch', '--prune', '--quiet', 'origin'], runner)
    path = f'handoff/outbox/{task_id}.md'
    try:
        text = _git(repo, ['show', f'origin/main:{path}'], runner)
    except RuntimeError:
        return {'ok': False, 'status': None, 'commits': {}, 'report': None,
                'problems': [f'отчёт {path} не найден в main на GitHub']}
    fields = {}
    for line in text.splitlines():
        key, separator, value = line.partition(':')
        if separator and key.strip().casefold() in ('status', 'commits') and key.strip().casefold() not in fields:
            fields[key.strip().casefold()] = value.split('#', 1)[0].strip()
    status = fields.get('status', '').split()[0].casefold() if fields.get('status') else None
    problems = [] if status in REPORT_STATUSES else ['в отчёте нет строки status: done | blocked | needs_owner']
    commits = {}
    for sha in dict.fromkeys(SHA.findall(fields.get('commits', ''))):
        try:
            _git(repo, ['cat-file', '-e', sha + '^{commit}'], runner)
            commits[sha] = bool(_git(repo, ['branch', '-r', '--contains', sha], runner).strip())
        except RuntimeError:
            commits[sha] = False
    missing = [sha for sha, found in commits.items() if not found]
    if missing:
        problems.append('на GitHub нет коммитов: ' + ', '.join(missing))
    return {'ok': not problems, 'status': status, 'commits': commits, 'report': text, 'problems': problems}


def record_verification(task_id, verification, path=None):
    state = read_state(path)
    record = state['tasks'][task_id]
    record['verification'] = {key: verification[key] for key in ('ok', 'status', 'commits', 'problems')}
    record['verified_at'] = utc_now()
    save_state(state, path)
    return record


def verification_text(task_id, verification):
    if verification['ok']:
        found = len(verification['commits'])
        return (f"✅ {task_id}: отчёт подтверждён в GitHub (статус {verification['status']}"
                + (f", коммитов найдено {found}/{found}" if found else '') + ").")
    return (f"⚠️ {task_id}: отчёт разработчика НЕ подтверждён в GitHub — "
            + '; '.join(verification['problems']) + ". Не считайте задание выполненным без проверки.")


def owner_card(task):
    return (f"📨 Задание от AI-тестировщика {task['id']}\n"
            f"Вид: {task['kind']}; приоритет: {task.get('priority') or 'P2'}\n"
            f"{task['title']}\n\n{task['body'][:1200]}"
            + ('…' if len(task['body']) > 1200 else '') +
            "\n\nПередать разработчику? Выпуск и действия с рабочими данными выполняются только после вашего решения. "
            "Если кнопок нет — откройте «☰ Ещё → 🧪 Ошибки тестировщика».")
