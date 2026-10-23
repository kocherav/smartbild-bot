import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import handoff_watcher as hw


def task_text(task_id='TASK-20261023-01', kind='code', title='Сверка прерванного счёта', body='Сделай сверку.', extra=''):
    return f'---\nid: {task_id}\nkind: {kind}\npriority: P1\ntitle: {title}\n{extra}---\n\n{body}\n'


class FakeGit:
    """Remote branches as {ref: {path: (text, commit_time)}}; records every command."""

    def __init__(self, branches):
        self.branches = branches
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
        if args[0] == 'show':
            ref, path = args[1].split(':', 1)
            return done(self.branches[ref.removeprefix('origin/')][path][0])
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
        allowed = {'fetch', 'rev-parse', 'for-each-ref', 'ls-tree', 'show', 'log'}
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


class BridgeHandoffTests(unittest.TestCase):
    def test_poll_dispatches_code_task_and_asks_owner_for_release(self):
        import bridge
        git = FakeGit({'claude/x': {
            'handoff/inbox/TASK-20261023-01.md': (task_text(), 10),
            'handoff/inbox/TASK-20261023-02.md': (task_text('TASK-20261023-02', 'release', 'Выпуск'), 11)}})
        sent = []
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(hw, 'STATE', Path(temporary) / 'handoff_state.json'), \
             patch.object(hw.subprocess, 'run', git), \
             patch.object(bridge, 'DEVELOPER_LOCK_FILE', str(Path(temporary) / 'developer.lock')), \
             patch.object(bridge, 'ask_developer', return_value='Сделано, отчёт в handoff/outbox.') as developer, \
             patch.object(bridge, 'send_message', side_effect=lambda token, chat, text, markup=None: sent.append((text, markup))):
            self.assertTrue(bridge.poll_handoff('token', 'owner'))
            self.assertEqual(1, developer.call_count)
            self.assertIn('Сделай сверку.', developer.call_args.args[0])
            self.assertEqual({'workdir': '/repo', 'fresh': True}, developer.call_args.kwargs)
            card = next(markup for text, markup in sent if 'TASK-20261023-02' in text and markup)
            self.assertIn('✅ Выполнить TASK-20261023-02', json.dumps(card, ensure_ascii=False))
            state = hw.read_state()
            self.assertEqual('done', state['tasks']['TASK-20261023-01']['status'])
            self.assertEqual('awaiting_owner', state['tasks']['TASK-20261023-02']['status'])
            with patch.object(bridge, 'run_background_job', side_effect=lambda job, *a, **k: job()):
                self.assertTrue(bridge.handle_global_navigation('token', 'owner', '✅ Выполнить TASK-20261023-02'))
            self.assertEqual(2, developer.call_count)
            self.assertEqual({'workdir': '/repo', 'fresh': True}, developer.call_args.kwargs)
            self.assertEqual('done', hw.read_state()['tasks']['TASK-20261023-02']['status'])
            self.assertTrue(bridge.handle_global_navigation('token', 'owner', '✅ Выполнить TASK-20261023-02'))
            self.assertEqual(2, developer.call_count, 'повторная кнопка не запускает разработчика')


if __name__ == '__main__':
    unittest.main()
