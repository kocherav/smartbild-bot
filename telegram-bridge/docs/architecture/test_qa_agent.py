import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import qa_agent


class QaAgentTests(unittest.TestCase):
    def test_production_atomic_save_grants_both_writers_even_when_current_writer_has_access(self):
        completed = Mock(returncode=0, stderr='')
        with patch.object(qa_agent.subprocess, 'run', return_value=completed) as run, \
             patch.object(qa_agent.os, 'replace'):
            qa_agent.atomic_save(qa_agent.DEFAULT_STATE, {'version': 1, 'runs': [], 'tasks': []})
        self.assertIn('u:smartbild-projects:rw,u:kocher.av:rw', ' '.join(run.call_args.args[0]))

    def test_success_creates_run_without_developer_task(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / 'receipt.json'
            receipt.write_text(json.dumps({'successful': True, 'tests': 12, 'cases': []}))
            result = qa_agent.inspect_receipt('full', receipt, qa_agent.Registry(Path(temporary) / 'state.json'))
            self.assertTrue(result['run']['successful'])
            self.assertIsNone(result['task'])

    def test_failure_creates_actionable_task_and_deduplicates_repeat(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / 'receipt.json'
            receipt.write_text(json.dumps({'successful': False, 'tests': 2, 'cases': [
                {'id': 'test_payment.PaymentTests.test_retry', 'status': 'failed'}]}))
            registry = qa_agent.Registry(Path(temporary) / 'state.json')
            first = qa_agent.inspect_receipt('full', receipt, registry)
            second = qa_agent.inspect_receipt('full', receipt, registry)
            self.assertEqual(first['task']['id'], second['task']['id'])
            self.assertEqual(2, second['task']['occurrences'])
            self.assertEqual('P1', first['task']['severity'])
            self.assertIn('корневую причину', first['developer_prompt'])
            self.assertIn('не повторять', first['developer_prompt'])

    def test_skip_and_isolation_attempt_are_release_failures(self):
        report = {'successful': True, 'cases': [{'id': 'test_x.test_y', 'status': 'skipped'}],
                  'blocked_events': [{'event': 'socket.connect'}]}
        failures = qa_agent.report_failures(report)
        self.assertEqual({'skipped', 'blocked'}, {item['status'] for item in failures})

    def test_blocked_case_keeps_its_infrastructure_identity(self):
        failures = qa_agent.report_failures({'successful': False, 'cases': [
            {'id': 'infra:playwright-browser', 'status': 'blocked'}]})
        self.assertEqual([{'id': 'infra:playwright-browser', 'status': 'blocked'}], failures)

    def test_unsuccessful_report_without_cases_cannot_be_green(self):
        self.assertEqual('runner:incomplete', qa_agent.report_failures({'successful': False})[0]['id'])

    def test_missing_human_journey_prevents_green_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'journeys.json'
            evidence = Path(temporary) / 'fixture.json'
            evidence.write_text('{"source":"crm-readonly"}')
            path.write_text(json.dumps({'journeys': [
                {'id': 'DONE', 'automated': True, 'test_case': 'human.done', 'fixture_provenance': {
                    'source': 'crm-readonly', 'captured_at': '2026-10-20T00:00:00Z', 'evidence': 'fixture.json',
                    'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}},
                {'id': 'MISSING', 'automated': False}]}))
            report = {'cases': [{'id': 'human.done', 'status': 'passed',
                                  'transcript': [{'actor': 'tester'}, {'actor': 'bot'}],
                                  'observations': [{'verdict': 'passed'}]}]}
            self.assertEqual([{'id': 'coverage:MISSING', 'status': 'missing'}], qa_agent.human_coverage_failures(path, report))
            self.assertEqual('missing', qa_agent.report_failures({
                'successful': False, 'cases': qa_agent.human_coverage_failures(path, report)})[0]['status'])
            self.assertEqual('P1', qa_agent.severity(qa_agent.human_coverage_failures(path, report)))

    def test_synthetic_human_fixture_cannot_count_as_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'journeys.json'
            path.write_text(json.dumps({'journeys': [{'id': 'STATUS', 'automated': True}]}))
            self.assertEqual(
                [{'id': 'coverage:STATUS:unverified-fixture', 'status': 'missing'}],
                qa_agent.human_coverage_failures(path),
            )

    def test_human_coverage_requires_executed_case_dialogue_readback_and_untampered_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = root / 'readonly.json'; evidence.write_text('{"deal":900}')
            path = root / 'journeys.json'
            path.write_text(json.dumps({'journeys': [{
                'id': 'STATUS', 'automated': True, 'test_case': 'human.status',
                'fixture_provenance': {'source': 'crm-readonly', 'captured_at': '2026-10-21T09:00:00Z',
                                       'evidence': 'readonly.json',
                                       'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}}]}))
            report = {'cases': [{'id': 'human.status', 'status': 'passed',
                                  'transcript': [{'actor': 'tester'}, {'actor': 'bot'}],
                                  'observations': [{'verdict': 'passed'}]}]}
            self.assertEqual([], qa_agent.human_coverage_failures(path, report))
            no_dialogue = json.loads(json.dumps(report)); no_dialogue['cases'][0].pop('transcript')
            self.assertEqual('coverage:STATUS:dialogue-missing', qa_agent.human_coverage_failures(path, no_dialogue)[0]['id'])
            evidence.write_text('{"deal":901}')
            self.assertEqual('coverage:STATUS:evidence-hash-mismatch', qa_agent.human_coverage_failures(path, report)[0]['id'])

    def test_corrupt_registry_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / 'state.json'
            state.write_text('{broken')
            with self.assertRaises(json.JSONDecodeError):
                qa_agent.Registry(state).read()

    def test_human_protocol_preserves_dialogue_and_developer_assignment(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / 'receipt.json'
            receipt.write_text(json.dumps({'successful': False, 'ran_at': 'now', 'cases': [{
                'id': 'human.test', 'status': 'failed',
                'transcript': [{'actor': 'tester', 'kind': 'message', 'text': 'Создай сделку'},
                               {'actor': 'bot', 'kind': 'message', 'text': 'Уточните клиента'}],
                'observations': [{'expected': 'preview', 'actual': 'уточнение', 'verdict': 'failed'}]}]}))
            registry = qa_agent.Registry(Path(temporary) / 'state.json')
            result = qa_agent.inspect_receipt('human', receipt, registry)
            protocol = Path(result['task']['protocol']).read_text()
            assignment = Path(result['task']['developer_assignment']).read_text()
            self.assertIn('Создай сделку', protocol)
            self.assertIn('Уточните клиента', protocol)
            self.assertIn(str(result['task']['protocol']), assignment)

    def test_dispatch_sends_prompt_and_requires_new_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / 'receipt.json'
            receipt.write_text(json.dumps({'successful': False, 'cases': [
                {'id': 'test_x.test_boundary', 'status': 'failed'}]}))
            registry = qa_agent.Registry(Path(temporary) / 'state.json')
            task = qa_agent.inspect_receipt('full', receipt, registry)['task']
            runner = Mock(return_value=Mock(returncode=0, stdout='fixed', stderr=''))
            dispatched = registry.dispatch(task['id'], ['developer-agent'], runner=runner)
            self.assertEqual('awaiting_verification', dispatched['status'])
            self.assertIn(task['id'], runner.call_args.kwargs['input'])
            self.assertEqual(['developer-agent'], runner.call_args.args[0])

    def test_failed_verification_requeues_same_task_for_repair(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / 'receipt.json'
            receipt.write_text(json.dumps({'successful': False, 'cases': [
                {'id': 'test_x.test_boundary', 'status': 'failed'}]}))
            registry = qa_agent.Registry(Path(temporary) / 'state.json')
            first = qa_agent.inspect_receipt('human', receipt, registry)['task']
            state = registry.read()
            state['tasks'][0]['status'] = 'awaiting_verification'
            qa_agent.atomic_save(registry.path, state)
            repeated = qa_agent.inspect_receipt('human', receipt, registry)['task']
            self.assertEqual(first['id'], repeated['id'])
            self.assertEqual('ready', repeated['status'])
            self.assertEqual(1, repeated['verification_failures'])

    def test_green_verification_closes_only_matching_profile_tasks(self):
        with tempfile.TemporaryDirectory() as temporary:
            state_path = Path(temporary) / 'state.json'
            state_path.write_text(json.dumps({'version': 1, 'runs': [], 'tasks': [
                {'id': 'QA-H', 'profile': 'human', 'status': 'awaiting_verification'},
                {'id': 'QA-F', 'profile': 'full', 'status': 'awaiting_verification'}]}))
            receipt = Path(temporary) / 'receipt.json'
            receipt.write_text(json.dumps({'successful': True, 'tests': 1, 'cases': []}))
            registry = qa_agent.Registry(state_path)
            result = qa_agent.inspect_receipt('human', receipt, registry)
            tasks = {item['id']: item for item in registry.read()['tasks']}
            self.assertEqual('closed', tasks['QA-H']['status'])
            self.assertEqual(result['run']['id'], tasks['QA-H']['verification_run'])
            self.assertEqual('awaiting_verification', tasks['QA-F']['status'])

    def test_concurrent_profiles_get_distinct_evidence_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = Mock(return_value=Mock(returncode=0, stdout='', stderr=''))
            with unittest.mock.patch.object(qa_agent, 'FULL_GATE', ['gate']):
                first = qa_agent.run_profile('browser', temporary, runner=runner)
                second = qa_agent.run_profile('browser', temporary, runner=runner)
            self.assertNotEqual(first.parent, second.parent)

    def test_browser_profile_classifies_missing_playwright_runtime_as_infrastructure(self):
        with tempfile.TemporaryDirectory() as temporary:
            runner = Mock(return_value=Mock(
                returncode=1, stdout="Executable doesn't exist at /cache/ms-playwright/chrome", stderr=''))
            receipt = qa_agent.run_profile('browser', temporary, runner=runner)
            report = json.loads(receipt.read_text())
        self.assertEqual([{'id': 'infra:playwright-browser', 'status': 'blocked'}], report['cases'])
        self.assertIn('--evidence', runner.call_args.args[0])


if __name__ == '__main__':
    unittest.main()


class HumanProfileTests(unittest.TestCase):
    def test_every_listed_case_of_a_journey_must_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'journeys.json'
            evidence = Path(temporary) / 'fixture.json'
            evidence.write_text('{}')
            provenance = {'source': 'crm-readonly', 'captured_at': 'x', 'evidence': 'fixture.json',
                          'sha256': hashlib.sha256(evidence.read_bytes()).hexdigest()}
            path.write_text(json.dumps({'journeys': [{'id': 'INVOICE', 'automated': True,
                'test_cases': ['h.issue', 'h.get'], 'fixture_provenance': provenance}]}))
            good = {'status': 'passed', 'transcript': [{'actor': 'tester'}, {'actor': 'bot'}],
                    'observations': [{'verdict': 'passed'}]}
            both = {'cases': [{'id': 'h.issue', **good}, {'id': 'h.get', **good}]}
            self.assertEqual([], qa_agent.human_coverage_failures(path, both))
            one = {'cases': [{'id': 'h.issue', **good}]}
            self.assertEqual([{'id': 'coverage:INVOICE:case-not-passed', 'status': 'missing'}],
                             qa_agent.human_coverage_failures(path, one))

    def test_human_profile_runs_all_human_suites_with_the_registry(self):
        calls = []
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return Mock(returncode=1, stdout='', stderr='')
        with tempfile.TemporaryDirectory() as temporary:
            qa_agent.run_profile('human', evidence_root=temporary, runner=runner)
        command, kwargs = calls[0]
        for module in ('test_human_journeys', 'test_human_journeys_edge', 'human_live_journeys'):
            self.assertIn(module, command)
        self.assertEqual(str(qa_agent.HUMAN_JOURNEYS), kwargs['env']['QA_HUMAN_REGISTRY'])

    def test_missing_snapshot_does_not_hide_a_code_defect(self):
        with tempfile.TemporaryDirectory() as temporary:
            receipt = Path(temporary) / 'receipt.json'
            receipt.write_text(json.dumps({'successful': False, 'cases': [
                {'id': 'test_human_journeys.InvoiceJourneys.test_get_existing_invoice', 'status': 'failed'},
                {'id': 'infra:crm-snapshot:test_read_deal', 'status': 'blocked'},
                {'id': 'coverage:HUMAN-INVOICE:unverified-fixture', 'status': 'missing'}]}))
            registry = qa_agent.Registry(Path(temporary) / 'state.json')
            result = qa_agent.inspect_receipt('human', receipt, registry)
            kinds = {qa_agent.task_kind(task): task for task in result['tasks']}
            self.assertEqual({'technical', 'external'}, set(kinds))
            self.assertEqual(['test_human_journeys.InvoiceJourneys.test_get_existing_invoice'],
                             [f['id'] for f in kinds['technical']['failures']])
            self.assertEqual(result['task']['id'], kinds['technical']['id'])
            # Next run: the code defect is fixed, the snapshot is still missing.
            registry_state = registry.read()
            next(t for t in registry_state['tasks'] if t['id'] == kinds['technical']['id'])['status'] = 'awaiting_verification'
            qa_agent.atomic_save(registry.path, registry_state)
            receipt.write_text(json.dumps({'successful': False, 'cases': [
                {'id': 'infra:crm-snapshot:test_read_deal', 'status': 'blocked'},
                {'id': 'coverage:HUMAN-INVOICE:unverified-fixture', 'status': 'missing'}]}))
            qa_agent.inspect_receipt('human', receipt, registry)
            self.assertEqual('closed', registry.task(kinds['technical']['id'])['status'])

    def test_repository_registry_is_consistent(self):
        registry = json.loads(qa_agent.HUMAN_JOURNEYS.read_text(encoding='utf-8'))
        ids = [item['id'] for item in registry['journeys']]
        self.assertEqual(len(ids), len(set(ids)))
        for item in registry['journeys']:
            if item.get('automated'):
                self.assertTrue(item.get('test_cases'), item['id'])
