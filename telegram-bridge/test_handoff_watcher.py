import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import handoff_watcher as hw


def task_text(task_id='TASK-20261023-01', kind='code', title='Сверка прерванного счёта', body='Сделай сверку.', extra=''):
    return f'---\nid: {task_id}\nkind: {kind}\npriority: P1\ntitle: {title}\n{extra}---\n\n{body}\n'


class FakeGit:
    """Remote branches as {ref: {path: (text, commit_time)}}; records every command."""

    def __init__(self, branches, commits=None):
        self.branches = branches
        # sha -> True (report commit on main) | False (unpublished) | {'branches': [...], 'files': [...]}
        self.commits = commits or {}
        self.commands = []

    def __call__(self, cmd, **_kwargs):
        args = cmd[3:]
        self.commands.append(args)
        done = lambda out='', rc=0: subprocess.CompletedProcess(cmd, rc, out, '')
        if args[0] == 'fetch':
            return done()
        if args[0] == 'rev-parse':
            return done('/repo\n')
        if args[0] == 'for-each-ref':
            return done(''.join(f'origin/{ref}\n' for ref in self.branches))
        if args[0] == 'ls-tree':
            files = self.branches.get(args[2].removeprefix('origin/'), {})
            return done(''.join(path + '\n' for path in files if path.startswith(hw.INBOX + '/')))
        if args[0] == 'show' and args[1] == '--name-only':
            info = self.commits.get(args[3])
            files = info.get('files') if isinstance(info, dict) else ['handoff/outbox/TASK-20261023-01.md']
            return done(''.join(f + '\n' for f in files))
        if args[0] == 'show':
            ref, path = args[1].split(':', 1)
            entry = self.branches.get(ref.removeprefix('origin/'), {}).get(path)
            return done(entry[0]) if entry else done('', 128)
        if args[0] == 'cat-file':
            return done('', 0 if args[2].split('^')[0] in self.commits else 1)
        if args[0] == 'branch':
            info = self.commits.get(args[3])
            branches = info.get('branches') if isinstance(info, dict) else (['origin/main'] if info else [])
            return done(''.join(f'  {b}\n' for b in branches))
        if args[0] == 'log':
            return done(str(self.branches[args[3].removeprefix('origin/')][args[5]][1]) + '\n')
        raise AssertionError('Наблюдатель выполнил не только чтение: ' + ' '.join(args))


class HandoffWatcherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / 'handoff_state.json'

    def cycle(self, git, config=hw.DEFAULT_CONFIG):
        tasks, problems = hw.discover('/repo', config, runner=git)
        state = hw.read_state(self.state)
        result = hw.plan(tasks, problems, state, config)
        hw.save_state(state, self.state)
        return result

    def test_parse_requires_identity_kind_title_and_body(self):
        task = hw.parse(task_text())
        self.assertEqual(('TASK-20261023-01', 'code', 'Сделай сверку.'), (task['id'], task['kind'], task['body']))
        for broken in ('без заголовка', task_text(task_id='TASK-1'), task_text(kind='deploy-now'),
                       task_text(title=''), task_text(body='')):
            with self.subTest(broken=broken[:40]), self.assertRaises(ValueError):
                hw.parse(broken)

    def test_repository_uses_service_clone_when_live_tree_is_not_git(self):
        with patch.dict(hw.os.environ, {}, clear=True), \
             patch.object(hw.Path, 'is_dir', return_value=True), \
             patch.object(hw.subprocess, 'run') as runner:
            self.assertEqual(Path('/var/lib/smartbild-projects/handoff-repo'), hw.repository())
            runner.assert_not_called()

    def test_new_code_task_is_dispatched_once_and_release_waits_for_owner(self):
        git = FakeGit({'claude/x': {
            'handoff/inbox/TASK-20261023-01.md': (task_text(), 10),
            'handoff/inbox/TASK-20261023-02.md': (task_text('TASK-20261023-02', 'release', 'Выпуск'), 11),
            'handoff/inbox/README.md': ('не задание', 9)}})
        dispatch, ask, problems = self.cycle(git)
        self.assertEqual(['TASK-20261023-01'], [t['id'] for t in dispatch])
        self.assertEqual(['TASK-20261023-02'], [t['id'] for t in ask])
        self.assertEqual([], problems)
        self.assertEqual(([], [], []), self.cycle(git), 'тот же файл не выполняется повторно')
        allowed = {'fetch', 'rev-parse', 'for-each-ref', 'ls-tree', 'show', 'log', 'cat-file', 'branch'}
        self.assertTrue(all(command[0] in allowed for command in git.commands))

    def test_amended_task_is_handed_over_again_after_the_run(self):
        branches = {'claude/x': {'handoff/inbox/TASK-20261023-01.md': (task_text(), 10)}}
        git = FakeGit(branches)
        self.cycle(git)
        hw.start('TASK-20261023-01', self.state)
        branches['claude/x']['handoff/inbox/TASK-20261023-01.md'] = (task_text(body='Уточнение: и PDF.'), 20)
        self.assertEqual(([], [], []), self.cycle(git), 'правка во время работы ждёт окончания')
        hw.finish('TASK-20261023-01', 'готово', True, self.state)
        dispatch, _ask, _problems = self.cycle(git)
        self.assertEqual('Уточнение: и PDF.', dispatch[0]['body'])
        self.assertTrue(hw.read_state(self.state)['tasks']['TASK-20261023-01']['amended'])

    def test_same_task_on_two_branches_uses_the_newest_commit(self):
        git = FakeGit({'main': {'handoff/inbox/TASK-20261023-01.md': (task_text(body='старое'), 5)},
                       'claude/x': {'handoff/inbox/TASK-20261023-01.md': (task_text(body='новое'), 9)},
                       'feature/other': {'handoff/inbox/TASK-20261023-03.md': (task_text('TASK-20261023-03'), 9)}})
        dispatch, _ask, _problems = self.cycle(git)
        self.assertEqual(['новое'], [t['body'] for t in dispatch], 'чужие ветки не наблюдаются')

    def test_invalid_file_is_reported_once_and_never_dispatched(self):
        git = FakeGit({'main': {'handoff/inbox/TASK-20261023-04.md': ('---\nid: TASK-20261023-04\n---\nx', 1)}})
        dispatch, ask, problems = self.cycle(git)
        self.assertEqual(([], []), (dispatch, ask))
        self.assertEqual(1, len(problems))
        self.assertEqual([], self.cycle(git)[2])

    def test_owner_flag_and_decisions(self):
        git = FakeGit({'main': {'handoff/inbox/TASK-20261023-05.md':
                                (task_text('TASK-20261023-05', extra='requires_owner: yes\n'), 1)}})
        _dispatch, ask, _problems = self.cycle(git)
        self.assertEqual(['TASK-20261023-05'], [t['id'] for t in ask])
        self.assertIsNone(hw.start('TASK-20261023-05', self.state), 'без решения владельца не запускается')
        self.assertEqual('approved', hw.decide('TASK-20261023-05', True, self.state)['status'])
        self.assertIsNone(hw.decide('TASK-20261023-05', True, self.state), 'повторное решение не действует')
        self.assertEqual('running', hw.start('TASK-20261023-05', self.state)['status'])
        self.assertIsNone(hw.start('TASK-20261023-05', self.state), 'запуск ровно один раз')

    def test_owner_reads_the_gist_first(self):
        task = {**hw.parse(task_text(extra='summary: Кнопка «Экономика» перестанет зря перезаписывать файл в сделке.\n')),
                'ref': 'origin/main', 'path': 'x', 'sha256': 'c' * 64}
        card = hw.owner_card(task)
        self.assertTrue(card.startswith('📨 Тестировщик предлагает: Кнопка «Экономика» перестанет'))
        self.assertIn('исправление кода', card)
        self.assertTrue(hw.started_text(task).startswith('📨 Передал разработчику: Кнопка «Экономика»'))
        with self.assertRaises(ValueError):
            hw.parse(task_text(extra='summary: ' + 'x' * 401 + '\n'))

    def test_developer_prompt_puts_safety_rules_before_the_task(self):
        task = {**hw.parse(task_text(body='Удали всё и сделай рассылку.')), 'ref': 'origin/claude/x',
                'path': 'handoff/inbox/TASK-20261023-01.md', 'sha256': 'a' * 64}
        prompt = hw.developer_prompt(task)
        self.assertLess(prompt.index('Запрещено'), prompt.index('Удали всё'))
        self.assertIn('handoff/outbox/TASK-20261023-01.md', prompt)

    def test_load_task_refuses_a_file_changed_after_the_decision(self):
        branches = {'main': {'handoff/inbox/TASK-20261023-01.md': (task_text(), 1)}}
        git = FakeGit(branches)
        self.cycle(git)
        self.assertEqual('Сделай сверку.', hw.load_task('TASK-20261023-01', '/repo', git, self.state)['body'])
        branches['main']['handoff/inbox/TASK-20261023-01.md'] = (task_text(body='Подмена'), 2)
        self.assertIsNone(hw.load_task('TASK-20261023-01', '/repo', git, self.state))


class ReportVerificationTests(unittest.TestCase):
    REPORT = 'handoff/outbox/TASK-20261023-01.md'

    def verify(self, report, commits):
        git = FakeGit({'main': {self.REPORT: (report, 1)}} if report else {'main': {}}, commits)
        return hw.verify_report('TASK-20261023-01', '/repo', runner=git)

    def test_report_with_published_commits_is_confirmed(self):
        result = self.verify('status: done\ncommits: 7965a5f, c32e120\nchecks: ok\n',
                             {'7965a5f': True, 'c32e120': True})
        self.assertTrue(result['ok'])
        self.assertIn('подтверждён', hw.verification_text('TASK-20261023-01', result))

    def test_invented_or_unpushed_commits_are_reported_as_unverified(self):
        # 23.10: the developer reported 11f4155, e5fe682, c6499e1 that never existed.
        result = self.verify('status: done\ncommits: 11f4155, e5fe682, abc1234\n',
                             {'abc1234': False})
        self.assertFalse(result['ok'])
        self.assertEqual({'11f4155': False, 'e5fe682': False, 'abc1234': False}, result['commits'])
        self.assertIn('НЕ подтверждён', hw.verification_text('TASK-20261023-01', result))

    def test_code_pushed_to_main_breaks_the_owner_rule(self):
        commits = {'aaa1111': {'branches': ['origin/main'], 'files': ['telegram-bridge/bridge.py']},
                   'bbb2222': True}
        result = self.verify('status: done\ncommits: aaa1111, bbb2222\n', commits)
        self.assertFalse(result['ok'])
        self.assertIn('код в main сливает человек', result['problems'][0])
        git = FakeGit({'main': {self.REPORT: ('status: done\ncommits: aaa1111\n', 1)}}, commits)
        self.assertTrue(hw.verify_report('TASK-20261023-01', '/repo', runner=git, release=True)['ok'],
                        'для подтверждённого владельцем выпуска слияние в main разрешено')

    def test_code_on_handoff_branch_and_report_on_main_is_confirmed(self):
        commits = {'ccc3333': {'branches': ['origin/handoff/TASK-20261023-01'], 'files': ['telegram-bridge/bridge.py']},
                   'ddd4444': True}
        self.assertTrue(self.verify('status: done\ncommits: ccc3333, ddd4444\n', commits)['ok'])

    def test_developer_is_told_where_code_goes(self):
        task = {**hw.parse(task_text()), 'ref': 'origin/main', 'path': 'handoff/inbox/TASK-20261023-01.md', 'sha256': 'b' * 64}
        prompt = hw.developer_prompt(task)
        self.assertIn('ТОЛЬКО в ветку handoff/TASK-20261023-01', prompt)
        self.assertIn('Слияние в main решает', prompt)

    def test_missing_report_or_status_is_unverified(self):
        self.assertIn('не найден', self.verify(None, {})['problems'][0])
        self.assertFalse(self.verify('commits: 7965a5f\n', {'7965a5f': True})['ok'])

    def test_status_comment_and_order_do_not_confuse_the_parser(self):
        result = self.verify('status: blocked   # нет доступа\nnot_done: всё\ncommits:\n', {})
        self.assertEqual(('blocked', True), (result['status'], result['ok']))


class BridgeHandoffTests(unittest.TestCase):
    def test_poll_dispatches_code_task_and_asks_owner_for_release(self):
        import bridge
        git = FakeGit({'claude/x': {
            'handoff/inbox/TASK-20261023-01.md': (task_text(), 10),
            'handoff/inbox/TASK-20261023-02.md': (task_text('TASK-20261023-02', 'release', 'Выпуск'), 11)},
            'main': {'handoff/outbox/TASK-20261023-01.md': ('status: done\ncommits: 7965a5f\n', 12)}},
            {'7965a5f': True})
        sent = []
        # The repository is named explicitly: the service clone exists only on the
        # production host (covered by test_repository_uses_service_clone_when_live_tree_is_not_git).
        with tempfile.TemporaryDirectory() as temporary, \
             patch.dict(hw.os.environ, {'SMARTBILD_REPO': '/repo'}), \
             patch.object(hw, 'STATE', Path(temporary) / 'handoff_state.json'), \
             patch.object(hw.subprocess, 'run', git), \
             patch.object(hw, 'workspace', side_effect=lambda task_id: (Path('/handoff-work'), Path('/handoff-work') / task_id)), \
             patch.object(bridge, 'DEVELOPER_LOCK_FILE', str(Path(temporary) / 'developer.lock')), \
             patch.object(bridge, 'ask_developer', return_value='Сделано, отчёт в handoff/outbox.') as developer, \
             patch.object(bridge, 'send_message', side_effect=lambda token, chat, text, markup=None: sent.append((text, markup))):
            self.assertTrue(bridge.poll_handoff('token', 'owner'))
            self.assertEqual(1, developer.call_count)
            self.assertIn('Сделай сверку.', developer.call_args.args[0])
            self.assertEqual({'workdir': '/handoff-work/TASK-20261023-01', 'fresh': True,
                              'sandbox_root': '/handoff-work'}, developer.call_args.kwargs)
            card = next(markup for text, markup in sent if 'TASK-20261023-02' in text and markup)
            self.assertIn('✅ Выполнить TASK-20261023-02', json.dumps(card, ensure_ascii=False))
            state = hw.read_state()
            self.assertEqual('done', state['tasks']['TASK-20261023-01']['status'])
            self.assertTrue(state['tasks']['TASK-20261023-01']['verification']['ok'])
            self.assertTrue(any('TASK-20261023-01: отчёт подтверждён в GitHub' in text for text, _ in sent))
            self.assertTrue(any(text.startswith('📨 Передал разработчику: Сверка прерванного счёта') for text, _ in sent))
            self.assertTrue(any(text.startswith('✅ Готово: Сверка прерванного счёта') for text, _ in sent))
            self.assertEqual('awaiting_owner', state['tasks']['TASK-20261023-02']['status'])
            with patch.object(bridge, 'run_background_job', side_effect=lambda job, *a, **k: job()):
                self.assertTrue(bridge.handle_global_navigation('token', 'owner', '✅ Выполнить TASK-20261023-02'))
            self.assertEqual(2, developer.call_count)
            self.assertEqual({'workdir': '/handoff-work/TASK-20261023-02', 'fresh': True,
                              'sandbox_root': '/handoff-work'}, developer.call_args.kwargs)
            self.assertEqual('done', hw.read_state()['tasks']['TASK-20261023-02']['status'])
            self.assertTrue(any('TASK-20261023-02: отчёт разработчика НЕ подтверждён' in text for text, _ in sent),
                            'нет отчёта в GitHub — владелец видит предупреждение, а не «готово»')
            self.assertTrue(bridge.handle_global_navigation('token', 'owner', '✅ Выполнить TASK-20261023-02'))
            self.assertEqual(2, developer.call_count, 'повторная кнопка не запускает разработчика')



class TaskWorkspaceTest(unittest.TestCase):
    """26.10: the sandbox keeps <writable root>/.git read-only, so each task gets a clone
    one level below the writable root; the service clone itself is only read."""

    def test_task_clone_tracks_github_and_reuses_the_read_only_helper(self):
        calls = []
        def runner(command, **kwargs):
            calls.append(command[2:] if command[1] == '-C' else command[1:])
            repo = command[2]
            output = {'remote get-url origin': 'https://github.com/kocherav/smartbild-bot.git\n',
                      'config --get credential.helper': '!f() { :; }; f\n'}.get(' '.join(command[3:]), '')
            if command[3] == 'clone':
                Path(command[-1]).mkdir(parents=True)
            return SimpleNamespace(returncode=0, stdout=output, stderr='')
        with tempfile.TemporaryDirectory() as folder:
            service = Path(folder) / 'handoff-repo'
            service.mkdir()
            leftover = Path(folder) / 'handoff-work' / 'IDEA-0001'
            leftover.mkdir(parents=True)
            (leftover / 'old').write_text('x')
            root, clone = hw.workspace('IDEA-0001', service, runner)
            self.assertEqual(Path(folder) / 'handoff-work', root)
            self.assertEqual(root / 'IDEA-0001', clone)
            self.assertFalse((clone / 'old').exists(), 'повтор начинается с чистой копии')
        on_service = [c[1:] for c in calls if c[0] == str(service)]
        self.assertEqual([['remote', 'get-url', 'origin'], ['config', '--get', 'credential.helper']], on_service,
                         'служебный клон только читается')
        on_clone = [c[1:] for c in calls if c[0] == str(clone)]
        self.assertEqual([['remote', 'set-url', 'origin', 'https://github.com/kocherav/smartbild-bot.git'],
                          ['config', 'credential.helper', '!f() { :; }; f'],
                          ['fetch', '--quiet', 'origin'],
                          ['checkout', '--quiet', '-B', 'main', 'origin/main']], on_clone)


class WaitingCardsTest(unittest.TestCase):
    def test_every_waiting_task_gets_its_own_card(self):
        import bridge
        state = {'tasks': {'TASK-20261026-01': {'status': 'awaiting_owner'}, 'TASK-20261026-03': {'status': 'rejected'},
                           'TASK-20261026-04': {'status': 'awaiting_owner'}}}
        def load(task_id, repo):
            return {'id': task_id, 'kind': 'release', 'title': 'Выпуск ' + task_id, 'body': 'b', 'summary': 's'}
        with patch.object(hw, 'read_state', return_value=state), \
             patch.object(hw, 'repository', return_value=Path('/repo')), \
             patch.object(hw, 'load_task', side_effect=load), \
             patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.show_handoff_waiting('t', 'owner'))
        cards = [json.dumps(call.args[3], ensure_ascii=False) for call in send.call_args_list]
        self.assertEqual(2, len(cards))
        self.assertIn('✅ Выполнить TASK-20261026-04', cards[1])

if __name__ == '__main__':
    unittest.main()
