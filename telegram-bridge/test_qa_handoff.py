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

    def test_autopilot_repairs_then_immediately_verifies_and_closes(self):
        broken = {'ok': True, 'task': {'id': 'QA-A1', 'status': 'ready',
                  'failures': [{'id': 'test:x', 'status': 'failed'}]}}
        green = {'ok': True, 'task': None}
        with patch.object(bridge.qa_autopilot, 'run', side_effect=[broken, green]) as run, \
             patch.object(bridge.qa_autopilot, 'approve_technical', return_value={
                 'id': 'QA-A1', 'status': 'approved'}), \
             patch.object(bridge, 'process_qa_developer_task', return_value=True) as developer, \
             patch.object(bridge.safe_reload, 'pending_reviewed', return_value=False), \
             patch.object(bridge, 'send_message'):
            self.assertTrue(bridge.run_qa_autopilot('token', 'owner', 'human'))
        self.assertEqual([unittest.mock.call('human'), unittest.mock.call('human')], run.call_args_list)
        developer.assert_called_once_with('token', 'owner', 'QA-A1')

    def test_autopilot_bounds_failed_repairs_and_leaves_work_for_next_cycle(self):
        task = {'ok': True, 'task': {'id': 'QA-A1', 'status': 'ready',
                'failures': [{'id': 'test:x', 'status': 'failed'}]}}
        with patch.object(bridge.qa_autopilot, 'run', side_effect=[task, task, task]), \
             patch.object(bridge.qa_autopilot, 'approve_technical', return_value={
                 'id': 'QA-A1', 'status': 'approved'}), \
             patch.object(bridge, 'process_qa_developer_task', return_value=True) as developer, \
             patch.object(bridge.safe_reload, 'pending_reviewed', return_value=False), \
             patch.object(bridge, 'send_message'):
            self.assertFalse(bridge.run_qa_autopilot('token', 'owner', 'human'))
        self.assertEqual(2, developer.call_count)

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


if __name__ == '__main__':
    unittest.main()
