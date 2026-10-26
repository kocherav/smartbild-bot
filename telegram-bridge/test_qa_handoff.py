import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import qa_handoff
import bridge


class QaHandoffTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / 'qa.json'
        self.path.write_text(json.dumps({'version': 1, 'runs': [], 'tasks': [{
            'id': 'QA-A1', 'status': 'ready', 'severity': 'P1', 'profile': 'human',
            'occurrences': 2, 'evidence': '/evidence.json',
            'failures': [{'id': 'HUMAN-DEAL-CREATE', 'status': 'failed'}]}]}))

    def test_owner_sees_short_summary_not_internal_prompt(self):
        task = qa_handoff.ready(self.path)[0]
        summary = qa_handoff.summarize(task)
        self.assertIn('QA-A1', summary); self.assertIn('Передать агенту-разработчику?', summary)
        self.assertNotIn('quality_gate', summary)

    def test_only_owner_approval_makes_task_claimable_once(self):
        self.assertIsNone(qa_handoff.claim('QA-A1', self.path))
        approved = qa_handoff.decide('QA-A1', True, self.path)
        self.assertEqual('approved', approved['status'])
        self.assertEqual('fixing', qa_handoff.claim('QA-A1', self.path)['status'])
        self.assertIsNone(qa_handoff.claim('QA-A1', self.path))
        finished = qa_handoff.finish('QA-A1', 'исправлено', True, self.path)
        self.assertEqual('awaiting_verification', finished['status'])

    def test_rejection_never_reaches_developer(self):
        self.assertEqual('dismissed', qa_handoff.decide('QA-A1', False, self.path)['status'])
        self.assertIsNone(qa_handoff.claim('QA-A1', self.path))

    def test_external_prerequisite_leaves_developer_queue(self):
        deferred = qa_handoff.defer_external('QA-A1', 'test account required', self.path)
        self.assertEqual('waiting_input', deferred['status'])
        self.assertIsNone(qa_handoff.claim('QA-A1', self.path))

    def test_satisfied_external_prerequisite_resumes_same_task(self):
        qa_handoff.defer_external('QA-A1', 'test account required', self.path)
        resumed = qa_handoff.resume_waiting('QA-A1', 'owner messages allowed', self.path)
        self.assertEqual('ready', resumed['status'])
        self.assertEqual('owner messages allowed', resumed['resume_reason'])

    def test_production_registry_grants_service_access_before_replace(self):
        completed = type('Completed', (), {'returncode': 0, 'stderr': ''})()
        with patch.object(qa_handoff.subprocess, 'run', return_value=completed) as run:
            qa_handoff._grant_shared_access('/tmp/qa-state')
        self.assertEqual('setfacl', run.call_args.args[0][0])
        self.assertIn('u:smartbild-projects:rw', run.call_args.args[0][2])

    def test_bot_starts_developer_only_after_inline_approval(self):
        jobs = []
        with patch.object(qa_handoff, 'STATE', self.path), patch.object(bridge, 'send_message'), \
             patch.object(bridge, 'run_background_job', side_effect=lambda job, *_a, **_k: jobs.append(job)):
            self.assertTrue(bridge.handle_global_navigation('token', 'owner', '✅ Передать разработчику QA-A1'))
            self.assertEqual(1, len(jobs))
            self.assertEqual('approved', qa_handoff._read(self.path)['tasks'][0]['status'])
            self.assertTrue(bridge.handle_global_navigation('token', 'owner', '✅ Передать разработчику QA-A1'))
            self.assertEqual(1, len(jobs))

    def test_background_registry_failure_is_logged_without_spamming_owner(self):
        with patch.object(qa_handoff, 'ready', side_effect=PermissionError('state denied')), \
             patch.object(bridge, 'send_message') as send, patch('builtins.print') as log:
            self.assertFalse(bridge.show_qa_findings('token', 'owner', only_unnotified=True))
        send.assert_not_called()
        self.assertIn('PermissionError', log.call_args.args[0])

    def test_autopilot_sends_a_repair_to_a_branch_once_and_does_not_reverify(self):
        # Owner rule 25.10: the fix waits for tester review and release; the same
        # cycle neither repeats the run nor dispatches a second repair.
        broken = {'ok': True, 'task': {'id': 'QA-A1', 'status': 'ready',
                  'failures': [{'id': 'test:x', 'status': 'failed'}]}}
        with patch.object(bridge.qa_autopilot, 'run', return_value=broken) as run, \
             patch.object(bridge.qa_autopilot, 'approve_technical', return_value={
                 'id': 'QA-A1', 'status': 'approved'}), \
             patch.object(bridge, 'process_qa_developer_task', return_value=True) as developer, \
             patch.object(bridge, 'send_message'):
            self.assertFalse(bridge.run_qa_autopilot('token', 'owner', 'human'))
        run.assert_called_once_with('human')
        developer.assert_called_once_with('token', 'owner', 'QA-A1')

    def test_repair_goes_to_branch_with_github_check_and_never_reloads_the_bot(self):
        task = {'id': 'QA-B2', 'status': 'fixing', 'severity': 'P1', 'profile': 'human',
                'failures': [{'id': 'test_x.Case.test_contract', 'status': 'failed'}]}
        report = {'ok': True, 'status': 'done', 'commits': {'abc1234': True}, 'report': 'status: done', 'problems': []}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(bridge.qa_handoff, 'claim', return_value=task), \
             patch.object(bridge.qa_handoff, 'finish') as finish, \
             patch.object(bridge.handoff_watcher, 'repository', return_value=Path(folder)), \
             patch.object(bridge.handoff_watcher, 'verify_report', return_value=report), \
             patch.object(bridge, 'DEVELOPER_LOCK_FILE', str(Path(folder) / 'dev.lock')), \
             patch.object(bridge, 'reload_snapshot', side_effect=[{'a.py': '1'}, {'a.py': '2'}]), \
             patch.object(bridge.safe_reload, 'request') as reload_request, \
             patch.object(bridge, 'ask_developer', return_value='Сделано') as developer, \
             patch.object(bridge, 'send_message') as send:
            self.assertTrue(bridge.process_qa_developer_task('token', 'owner', 'QA-B2'))
        prompt = developer.call_args.args[0]
        self.assertIn('handoff/QA-B2', prompt)
        self.assertEqual(folder, developer.call_args.kwargs['workdir'])
        self.assertTrue(developer.call_args.kwargs['fresh'])
        self.assertEqual('awaiting_release', finish.call_args.kwargs['status'])
        reload_request.assert_not_called()
        self.assertIn('в обход ветки', send.call_args.args[2])

    def test_autopilot_yields_before_verification_when_reload_is_pending(self):
        task = {'ok': True, 'task': {'id': 'QA-A1', 'status': 'ready',
                'failures': [{'id': 'test:x', 'status': 'failed'}]}}
        with patch.object(bridge.qa_autopilot, 'run', return_value=task) as run, \
             patch.object(bridge.qa_autopilot, 'approve_technical', return_value={
                 'id': 'QA-A1', 'status': 'approved'}), \
             patch.object(bridge, 'process_qa_developer_task', return_value=True), \
             patch.object(bridge.safe_reload, 'pending_reviewed', return_value=True), \
             patch.object(bridge, 'send_message'):
            self.assertFalse(bridge.run_qa_autopilot('token', 'owner', 'human'))
        run.assert_called_once_with('human')

    def test_autopilot_does_not_send_external_coverage_to_developer(self):
        task = {'ok': True, 'task': {'id': 'QA-A1', 'status': 'approved',
                'failures': [{'id': 'coverage:HUMAN-DEAL-CREATE', 'status': 'missing'}]}}
        with patch.object(bridge.qa_autopilot, 'run', return_value=task), \
             patch.object(bridge.qa_autopilot, 'defer_external', return_value={
                 'id': 'QA-A1', 'status': 'waiting_input'}), \
             patch.object(bridge, 'process_qa_developer_task') as developer:
            self.assertFalse(bridge.run_qa_autopilot('token', 'owner', 'human'))
        developer.assert_not_called()

    def test_autopilot_repairs_code_defect_even_when_snapshot_is_missing(self):
        external = {'id': 'QA-EXT', 'status': 'ready',
                    'failures': [{'id': 'coverage:HUMAN-INVOICE:unverified-fixture', 'status': 'missing'}]}
        technical = {'id': 'QA-TECH', 'status': 'ready',
                     'failures': [{'id': 'test_human_journeys.InvoiceJourneys.test_x', 'status': 'failed'}]}
        broken = {'ok': True, 'task': technical, 'tasks': [technical, external]}
        later = {'ok': True, 'task': external, 'tasks': [external]}
        with patch.object(bridge.qa_autopilot, 'run', side_effect=[broken, later]), \
             patch.object(bridge.qa_autopilot, 'defer_external') as defer, \
             patch.object(bridge.qa_autopilot, 'approve_technical', return_value={'id': 'QA-TECH', 'status': 'approved'}), \
             patch.object(bridge, 'process_qa_developer_task', return_value=True) as developer, \
             patch.object(bridge.safe_reload, 'pending_reviewed', return_value=False), \
             patch.object(bridge, 'send_message'):
            self.assertFalse(bridge.run_qa_autopilot('token', 'owner', 'human'))
        developer.assert_called_once_with('token', 'owner', 'QA-TECH')
        self.assertIn(unittest.mock.call(external), defer.call_args_list)

    def test_autopilot_does_not_dispatch_missing_human_evidence(self):
        task = {'ok': True, 'task': {'id': 'QA-A1', 'status': 'ready',
                'failures': [{'id': 'coverage:HUMAN-DEAL-CREATE', 'status': 'failed'}]}}
        with patch.object(bridge.qa_autopilot, 'run', return_value=task), \
             patch.object(bridge.qa_autopilot, 'defer_external', return_value={
                 'id': 'QA-A1', 'status': 'waiting_input'}), \
             patch.object(bridge, 'process_qa_developer_task') as developer, \
             patch.object(bridge, 'send_message'):
            self.assertFalse(bridge.run_qa_autopilot('token', 'owner', 'human'))
        developer.assert_not_called()

    def test_autopilot_does_not_dispatch_human_gap_after_owner_source_permission(self):
        task = {'ok': True, 'task': {'id': 'QA-A1', 'status': 'ready',
                'failures': [{'id': 'coverage:HUMAN-DEAL-CREATE', 'status': 'missing'}]}}
        with patch.object(bridge.qa_autopilot, 'run', return_value=task), \
             patch.object(bridge.qa_autopilot, 'owner_messages_allowed', return_value=True), \
             patch.object(bridge.qa_autopilot.qa_handoff, 'defer_external', return_value={
                 'id': 'QA-A1', 'status': 'waiting_input'}), \
             patch.object(bridge, 'process_qa_developer_task') as developer:
            self.assertFalse(bridge.run_qa_autopilot('token', 'owner', 'human'))
        developer.assert_not_called()



class AclSpecTest(unittest.TestCase):
    def test_owner_as_service_user_is_listed_once(self):
        from unittest.mock import patch
        with patch.object(qa_handoff, 'QA_SERVICE_USER', 'kocher.av'):
            self.assertEqual('u:kocher.av:rw,m:rw', qa_handoff.acl_spec())
        with patch.object(qa_handoff, 'QA_SERVICE_USER', 'smartbild-projects'):
            self.assertEqual('u:smartbild-projects:rw,u:kocher.av:rw,m:rw', qa_handoff.acl_spec())


class DeveloperSandboxTest(unittest.TestCase):
    def test_service_clone_git_metadata_is_writable(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / '.git').mkdir()
            with patch.object(bridge.subprocess, 'run') as run:
                bridge._run_developer_codex('', 'задача', folder)
            command = run.call_args.args[0]
            roots = next(arg for arg in command if arg.startswith('sandbox_workspace_write.writable_roots='))
            self.assertIn(str(Path(folder) / '.git'), json.loads(roots.split('=', 1)[1]))

if __name__ == '__main__':
    unittest.main()
