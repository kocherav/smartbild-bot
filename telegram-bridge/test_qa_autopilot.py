import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import qa_autopilot
import bridge


class AutopilotTest(unittest.TestCase):
    def test_night_window_is_moscow_midnight_to_seven(self):
        self.assertTrue(bridge.nightly_qa_window(dt.datetime(2026,10,21,21,0,tzinfo=dt.timezone.utc)))
        self.assertTrue(bridge.nightly_qa_window(dt.datetime(2026,10,22,3,59,tzinfo=dt.timezone.utc)))
        self.assertFalse(bridge.nightly_qa_window(dt.datetime(2026,10,22,4,0,tzinfo=dt.timezone.utc)))
        with self.assertRaises(ValueError):
            bridge.nightly_qa_window(dt.datetime(2026,10,22,1,0))

    def test_night_profiles_are_serial_and_stop_for_reload(self):
        calls=[]
        with patch.object(bridge,'run_qa_autopilot',side_effect=lambda token,chat,profile:calls.append(profile)), \
             patch.object(bridge.safe_reload,'pending_reviewed',side_effect=[False,False,False]):
            self.assertEqual(['full','browser','human'],bridge.run_nightly_qa('t','c'))
        self.assertEqual(['full','browser','human'],calls)
        calls.clear()
        with patch.object(bridge,'run_qa_autopilot',side_effect=lambda token,chat,profile:calls.append(profile)), \
             patch.object(bridge.safe_reload,'pending_reviewed',return_value=True):
            self.assertEqual(['full'],bridge.run_nightly_qa('t','c'))
        self.assertEqual(['full'],calls)

    def test_runner_receipt_is_parsed(self):
        runner = Mock(return_value=Mock(returncode=0, stdout=json.dumps({'run': {'id': 'R'}, 'task': None}), stderr=''))
        result = qa_autopilot.run(runner=runner)
        self.assertTrue(result['ok'])
        self.assertEqual('R', result['run']['id'])

    def test_technical_failure_is_approved_without_owner(self):
        task = {'id': 'QA-X', 'status': 'ready', 'failures': [{'id': 'test:deal-create'}]}
        with patch.object(qa_autopilot.qa_handoff, 'decide', return_value={'id': 'QA-X', 'status': 'approved'}) as decide:
            self.assertEqual('approved', qa_autopilot.approve_technical(task)['status'])
        decide.assert_called_once_with('QA-X', True)

    def test_missing_human_evidence_is_not_autoapproved(self):
        task = {'id': 'QA-X', 'status': 'ready',
                'failures': [{'id': 'coverage:HUMAN-DEAL-CREATE'}]}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(qa_autopilot, 'HUMAN_POLICY', Path(folder) / 'missing.json'), \
             patch.object(qa_autopilot.qa_handoff, 'decide') as decide:
            self.assertIsNone(qa_autopilot.approve_technical(task))
        decide.assert_not_called()

    def test_owner_permission_does_not_turn_missing_dialogue_into_code_work(self):
        task = {'id': 'QA-X', 'status': 'ready',
                'failures': [{'id': 'coverage:HUMAN-DEAL-CREATE'}]}
        with tempfile.TemporaryDirectory() as folder:
            policy = Path(folder) / 'policy.json'
            policy.write_text(json.dumps({'owner_messages_readonly': True}))
            self.assertFalse(qa_autopilot.technical(task, policy))

    def test_business_decision_is_not_autoapproved(self):
        task = {'id': 'QA-X', 'status': 'ready', 'failures': [{'id': 'decision:choose-tax'}]}
        with patch.object(qa_autopilot.qa_handoff, 'decide') as decide:
            self.assertIsNone(qa_autopilot.approve_technical(task))
        decide.assert_not_called()

    def test_infrastructure_failure_is_not_autoapproved_as_code_work(self):
        task = {'id': 'QA-X', 'status': 'ready',
                'failures': [{'id': 'infra:playwright-browser'}]}
        with patch.object(qa_autopilot.qa_handoff, 'decide') as decide:
            self.assertIsNone(qa_autopilot.approve_technical(task))
        decide.assert_not_called()

    def test_preapproved_retry_is_returned_without_owner_decision(self):
        task = {'id': 'QA-X', 'status': 'approved', 'failures': [{'id': 'test:x'}]}
        with patch.object(qa_autopilot.qa_handoff, 'decide') as decide:
            self.assertIs(task, qa_autopilot.approve_technical(task))
        decide.assert_not_called()

    def test_external_coverage_is_deferred_out_of_developer_queue(self):
        task = {'id': 'QA-X', 'status': 'approved',
                'failures': [{'id': 'coverage:HUMAN-DEAL-CREATE'}]}
        with tempfile.TemporaryDirectory() as folder, \
             patch.object(qa_autopilot, 'HUMAN_POLICY', Path(folder) / 'missing.json'), \
             patch.object(qa_autopilot.qa_handoff, 'defer_external',
                          return_value={'id': 'QA-X', 'status': 'waiting_input'}) as defer:
            result = qa_autopilot.defer_external(task)
        self.assertEqual('waiting_input', result['status'])
        defer.assert_called_once()

    def test_digest_reports_only_current_day(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            path.write_text(json.dumps({'version': 1, 'runs': [
                {'at': '2026-10-21T08:00:00+00:00', 'successful': True},
                {'at': '2026-10-20T08:00:00+00:00', 'successful': False}], 'tasks': []}))
            text = qa_autopilot.digest(path, dt.datetime(2026, 10, 21, tzinfo=dt.timezone.utc))
        self.assertIn('Прогонов: 1', text)


if __name__ == '__main__':
    unittest.main()
