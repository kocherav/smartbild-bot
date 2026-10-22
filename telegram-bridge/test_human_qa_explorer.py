import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import human_qa_explorer as explorer
from human_qa_harness import Stand
from test_human_journeys import office


class ScriptedBrain:
    """Plays the actor from a list, then answers as the judge."""

    def __init__(self, actions, verdict):
        self.actions, self.verdict, self.prompts = list(actions), verdict, []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if prompt.startswith(explorer.JUDGE_RULES[:40]):
            return 'Оценка:\n' + json.dumps(self.verdict, ensure_ascii=False)
        return json.dumps(self.actions.pop(0) if self.actions else {'action': 'finish'}, ensure_ascii=False)


MISSION = {'id': 'payer', 'goal': 'Смени плательщика в сделке 990001 на ООО «Альфа Сервис»',
           'success': ['плательщик 7102']}


class ExplorerTests(unittest.TestCase):
    def run_mission(self, actions, verdict):
        brain = ScriptedBrain(actions, verdict)
        stand = Stand()
        self.addCleanup(stand.close)
        office(stand.crm)
        decisions = explorer.explore(MISSION, brain, stand)
        receipt = stand.receipt()
        case = explorer.case_from(MISSION, receipt, explorer.judge(MISSION, receipt, brain), decisions)
        return brain, stand, case

    def test_actor_sees_screen_and_only_visible_buttons(self):
        brain, stand, case = self.run_mission([
            {'action': 'say', 'value': 'поменяй плательщика в сделке 990001 на альфа сервис'},
            {'action': 'press', 'value': 'Кнопка, которой нет'},
            {'action': 'press', 'value': '✅ Сменить плательщика'},
            {'action': 'finish'}], {'achieved': True, 'defects': [], 'summary': 'ok'})
        self.assertEqual('7102', stand.crm.deals['990001']['payer_id'])
        self.assertEqual('passed', case['status'])
        self.assertIn('invalid', case['decisions'][1])
        second_prompt = brain.prompts[1]
        self.assertIn('✅ Сменить плательщика', second_prompt)
        self.assertIn('Новый плательщик: ООО «Альфа Сервис»', second_prompt)
        judge_prompt = brain.prompts[-1]
        self.assertIn('payer_manager', judge_prompt)
        self.assertIn('Человек написал: поменяй плательщика', judge_prompt)

    def test_judge_defects_fail_the_case_with_evidence(self):
        _brain, _stand, case = self.run_mission([{'action': 'say', 'value': 'привет'}, {'action': 'finish'}], {
            'achieved': False, 'summary': 'цель не достигнута',
            'defects': [{'severity': 'P2', 'title': 'Бот не понял просьбу', 'evidence': 'шаг 1', 'expected': 'вопрос'}]})
        self.assertEqual('failed', case['status'])
        self.assertEqual('explore:payer', case['id'])
        self.assertTrue(any('Бот не понял' in o['actual'] for o in case['observations']))

    def test_minor_defect_alone_does_not_fail_an_achieved_goal(self):
        _brain, _stand, case = self.run_mission([{'action': 'finish'}], {
            'achieved': True, 'summary': 'ok', 'defects': [{'severity': 'P3', 'title': 'длинный текст'}]})
        self.assertEqual('passed', case['status'])
        self.assertEqual('failed', case['observations'][1]['verdict'])

    def test_rotation_is_stable_and_covers_all_missions(self):
        missions = explorer.load_missions()
        first = explorer.choose(missions, 4, '2026-10-22')
        self.assertEqual(first, explorer.choose(missions, 4, '2026-10-22'))
        seen = set()
        for day in range(1, 31):
            seen |= {m['id'] for m in explorer.choose(missions, 4, f'2026-11-{day:02d}')}
        self.assertEqual({m['id'] for m in missions}, seen)

    def test_main_writes_receipt_for_qa_agent(self):
        brain = ScriptedBrain([{'action': 'finish'}] * 3, {'achieved': True, 'defects': [], 'summary': 'ok'})
        with tempfile.TemporaryDirectory() as temporary, \
             patch.object(explorer, 'CodexBrain', return_value=brain):
            code = explorer.main(['--output', temporary, '--mission', 'deal-facts', '--scripted-bot'])
            report = json.loads((Path(temporary) / 'LAST_TEST_RUN.json').read_text())
        self.assertEqual(0, code)
        self.assertEqual(['explore:deal-facts'], [c['id'] for c in report['cases']])


if __name__ == '__main__':
    unittest.main()
