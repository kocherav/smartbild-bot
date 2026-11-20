import datetime as dt
import json
import subprocess
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
             patch.object(bridge.safe_reload,'pending_reviewed',side_effect=[False,False,False,False]):
            self.assertEqual(['full','browser','human','explore'],bridge.run_nightly_qa('t','c'))
        self.assertEqual(['full','browser','human','explore'],calls)
        calls.clear()
        with patch.object(bridge,'run_qa_autopilot',side_effect=lambda token,chat,profile:calls.append(profile)), \
             patch.object(bridge.safe_reload,'pending_reviewed',return_value=True):
            self.assertEqual(['full'],bridge.run_nightly_qa('t','c'))
        self.assertEqual(['full'],calls)

    def test_explorer_findings_wait_for_owner_review(self):
        task = {'id': 'QA-E', 'status': 'ready', 'failures': [
            {'id': 'explore:payer-voice', 'status': 'failed', 'title': 'Бот не понял голосовую фразу', 'severity': 'P2'}]}
        self.assertFalse(qa_autopilot.technical(task))
        self.assertIsNone(qa_autopilot.defer_external(task))
        self.assertIsNone(qa_autopilot.approve_technical(task))
        self.assertIn('Бот не понял голосовую фразу', qa_autopilot.qa_handoff.summarize(task))

    def test_runner_receipt_is_parsed(self):
        runner = Mock(return_value=Mock(returncode=0, stdout=json.dumps({'run': {'id': 'R'}, 'task': None}), stderr=''))
        result = qa_autopilot.run(runner=runner)
        self.assertTrue(result['ok'])
        self.assertEqual('R', result['run']['id'])

    def test_production_runner_uses_killable_process_group(self):
        completed = subprocess.CompletedProcess(['qa'], 0,
            json.dumps({'run': {'id': 'R'}, 'task': None}), '')
        with patch.object(qa_autopilot, '_run_process_group', return_value=completed) as run:
            result = qa_autopilot.run()
        self.assertTrue(result['ok'])
        self.assertTrue(run.call_args.kwargs['text'])
        self.assertEqual(3600, run.call_args.kwargs['timeout'])
        self.assertEqual(subprocess.PIPE, run.call_args.kwargs['stdout'])

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


    def test_repeated_runs_with_only_planned_coverage_are_not_problems(self):
        # 17.11: the owner read «5 прогонов; 1 успешный; 4 с замечаниями» as four failures.
        planned_gap = [{'id': 'coverage:HUMAN-PROCUREMENT'}, {'id': 'coverage:HUMAN-INSTALLATION'}]
        runs = [{'at': f'2026-11-17T{h:02d}:40:00+00:00', 'profile': 'human', 'successful': False,
                 'failures': planned_gap} for h in (0, 4, 8, 12)]
        runs += [{'at': '2026-11-17T01:01:00+00:00', 'profile': 'full', 'successful': True},
                 {'at': '2026-11-17T21:01:00+00:00', 'profile': 'browser', 'successful': False,
                  'failures': [{'id': 'infra:playwright-browser'}]}]
        tasks = [{'id': 'QA-H', 'status': 'waiting_input', 'failures': planned_gap}]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            path.write_text(json.dumps({'runs': runs, 'tasks': tasks}))
            text = qa_autopilot.digest(path, dt.datetime(2026, 11, 17, 22, tzinfo=dt.timezone.utc))
        self.assertIn('Прогонов: 6; без проблем: 5; с проблемами: 1.', text)
        self.assertIn('• browser: на сервере не запускается браузер', text)
        self.assertNotIn('• human', text)
        self.assertIn('Ещё не автоматизированы (в плане тестировщика)', text)

    def test_a_problem_repeated_in_several_runs_is_named_once_with_a_count(self):
        runs = [{'at': f'2026-11-17T{h:02d}:00:00+00:00', 'profile': 'explore', 'successful': False,
                 'failures': [{'id': 'infra:explore-no-receipt'}]} for h in (1, 2)]
        runs.append({'at': '2026-11-17T03:00:00+00:00', 'profile': 'explore', 'successful': True})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            path.write_text(json.dumps({'runs': runs, 'tasks': []}))
            text = qa_autopilot.digest(path, dt.datetime(2026, 11, 17, 22, tzinfo=dt.timezone.utc))
        self.assertEqual(1, text.count('модель не ответила вовремя'))
        self.assertIn('• explore (2 из 3 прогонов):', text)

    def test_digest_tells_what_each_task_is_about_and_who_acts(self):
        now = dt.datetime(2026, 10, 24, 15, 0, tzinfo=dt.timezone.utc)
        tasks = [{'id': f'QA-W{n}', 'status': 'waiting_input', 'severity': 'P1',
                  'failures': [{'id': f'coverage:HUMAN-DEAL-READ:{n}'}]} for n in range(6)]
        tasks.append({'id': 'QA-C', 'status': 'awaiting_verification', 'severity': 'P2',
                      'failures': [{'id': 'explore:assign', 'title': 'Нет кнопки назначения исполнителя'}]})
        state = {'runs': [{'at': '2026-10-24T01:00:00+00:00', 'profile': 'browser', 'successful': False,
                           'failures': [{'id': 'infra:playwright-browser'}]}], 'tasks': tasks}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'qa.json'
            path.write_text(json.dumps(state, ensure_ascii=False))
            journeys = Path(temporary) / 'journeys.json'
            journeys.write_text(json.dumps({'journeys': [
                {'id': 'HUMAN-DEAL-READ', 'title': 'Найти сделку и прочитать из неё информацию'}]}, ensure_ascii=False))
            text = qa_autopilot.digest(path, now, journeys)
        self.assertIn('browser: на сервере не запускается браузер', text)
        self.assertIn('Нет кнопки назначения исполнителя — исправлено, тестировщик перепроверит', text)
        self.assertIn('«Найти сделку и прочитать из неё информацию» не подтверждён', text)
        self.assertIn('…и ещё 1.', text)
        self.assertNotIn('waiting_input', text)



    def test_planned_journeys_are_not_shown_as_waiting_for_data(self):
        now = dt.datetime(2026, 10, 26, 15, 0, tzinfo=dt.timezone.utc)
        state = {'runs': [], 'tasks': [{'id': 'QA-P', 'status': 'waiting_input', 'severity': 'P1', 'failures': [
            {'id': 'coverage:HUMAN-PROCUREMENT'}, {'id': 'coverage:HUMAN-CONTRACT:evidence-missing'}]}]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'qa.json'
            path.write_text(json.dumps(state, ensure_ascii=False))
            journeys = Path(temporary) / 'journeys.json'
            journeys.write_text(json.dumps({'journeys': [
                {'id': 'HUMAN-PROCUREMENT', 'title': 'Учесть счёт поставщика'},
                {'id': 'HUMAN-CONTRACT', 'title': 'Подготовить договор по сделке'}]}, ensure_ascii=False))
            text = qa_autopilot.digest(path, now, journeys)
        self.assertIn('Ещё не автоматизированы (в плане тестировщика): «Учесть счёт поставщика».', text)
        self.assertIn('для маршрута «Подготовить договор по сделке» нет файла снимка CRM', text)
        self.assertNotIn('«Учесть счёт поставщика» не подтверждён', text)

if __name__ == '__main__':
    unittest.main()
