import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bridge
import qa_ideas
from human_qa_harness import FakeTelegram


NOW = dt.datetime(2026, 10, 30, 15, 0, tzinfo=dt.timezone.utc)  # пятница
RUNS = {'runs': [
    {'at': '2026-10-30T01:00:00+00:00', 'ideas': [
        {'title': 'Подсказывать счёт после статуса', 'value': 'средняя'},
        {'title': 'Кнопка счёта в карточке', 'why': '8 нажатий', 'how': 'кнопка', 'value': 'высокая',
         'mission': 'invoice-full'}]},
    {'at': '2026-10-30T02:00:00+00:00', 'ideas': [{'title': 'кнопка  счёта в карточке', 'value': 'высокая'}]},
    {'at': '2026-10-27T02:00:00+00:00', 'ideas': [{'title': 'Старая идея'}]}]}


class IdeasRegistryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'qa_ideas_state.json'

    def test_recent_ideas_once_and_most_valuable_first(self):
        ideas = qa_ideas.recent(RUNS, NOW)
        self.assertEqual(['Кнопка счёта в карточке', 'Подсказывать счёт после статуса'], [i['title'] for i in ideas])

    def test_decided_idea_is_not_offered_again(self):
        first = qa_ideas.register(qa_ideas.recent(RUNS, NOW), self.path, NOW)
        self.assertEqual(2, len(first))
        qa_ideas.decide(first[0]['id'], False, self.path)
        again = qa_ideas.register(qa_ideas.recent(RUNS, NOW), self.path, NOW)
        self.assertEqual(['Подсказывать счёт после статуса'], [i['title'] for i in again])
        self.assertIsNone(qa_ideas.decide(first[0]['id'], True, self.path), 'Повторное решение не меняет первое')

    def test_card_has_two_buttons_per_idea_and_counts_the_rest(self):
        ideas = [{'id': f'IDEA-0000000{n}', 'title': f'Идея {n}', 'value': 'средняя'} for n in range(7)]
        text, keyboard = qa_ideas.card(ideas)
        self.assertIn('…и ещё 2', text)
        self.assertEqual(['✅ Берём IDEA-00000000', '🚫 Не надо IDEA-00000000'],
                         [b['text'] for b in keyboard['keyboard'][0]])
        self.assertEqual(6, len(keyboard['keyboard']))

    def test_taken_idea_becomes_a_handoff_task_once(self):
        record = qa_ideas.register(qa_ideas.recent(RUNS, NOW), self.path, NOW)[0]
        qa_ideas.decide(record['id'], True, self.path)
        claimed = qa_ideas.start(record['id'], self.path)
        self.assertEqual('running', claimed['status'])
        self.assertIsNone(qa_ideas.start(record['id'], self.path))
        task = qa_ideas.developer_task(claimed)
        prompt = bridge.handoff_watcher.developer_prompt(task)
        self.assertIn('handoff/' + record['id'], prompt)
        self.assertIn('8 нажатий', prompt)

    def test_weekly_review_lists_every_idea_with_its_fate(self):
        records = qa_ideas.register(qa_ideas.recent(RUNS, NOW), self.path, NOW)
        qa_ideas.decide(records[0]['id'], True, self.path)
        text = qa_ideas.weekly_text(self.path, NOW)
        self.assertIn('за неделю: 2', text)
        self.assertIn('Ждут решения: 1; взяты: 1; не берём: 0', text)
        self.assertIn('Кнопка счёта в карточке — взята', text)


class IdeasOwnerFlowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.telegram = FakeTelegram('owner')
        folder = Path(self.temp.name)
        for patcher in (patch.object(qa_ideas, 'STATE', folder / 'qa_ideas_state.json'),
                        patch.object(bridge, 'tg_api', side_effect=self.telegram.api),
                        patch.object(bridge, 'DEAL_UI_STATE_FILE', str(folder / 'state.json')),
                        patch.object(bridge, 'DEAL_UI_STATE_LOCK_FILE', str(folder / 'state.lock')),
                        patch.object(bridge, 'DEVELOPER_LOCK_FILE', str(folder / 'dev.lock')),
                        patch.object(bridge.qa_handoff, '_read', return_value=RUNS),
                        patch.object(bridge.qa_autopilot, 'digest', return_value='🧪 сводка'),
                        patch.object(bridge, 'qa_night_plan', return_value='план ночи')):
            patcher.start()
            self.addCleanup(patcher.stop)

    def texts(self):
        return [event['text'] for event in self.telegram.events]

    def test_digest_then_ideas_with_buttons_then_friday_review(self):
        bridge.send_owner_digest('qa', 'owner', now=NOW)
        texts = self.texts()
        self.assertEqual('🧪 сводка\n\nплан ночи', texts[0])
        self.assertIn('Кнопка счёта в карточке', texts[1])
        self.assertIn('Идеи тестировщика за неделю', texts[2])
        ident = qa_ideas.idea_id('Кнопка счёта в карточке')
        self.assertIn('✅ Берём ' + ident, self.telegram.events[1]['keyboard'])

    def test_take_button_hands_the_idea_to_the_developer_once(self):
        bridge.send_owner_digest('qa', 'owner', now=NOW)
        ident = qa_ideas.idea_id('Кнопка счёта в карточке')
        report = {'ok': True, 'status': 'done', 'commits': {'abc1234': True}, 'report': 'status: done', 'problems': []}
        with (patch.object(bridge, 'run_background_job', side_effect=lambda job, *a, **k: job()),
              patch.object(bridge.handoff_watcher, 'repository', return_value=Path(self.temp.name)),
              patch.object(bridge.handoff_watcher, 'verify_report', return_value=report) as verify,
              patch.object(bridge, 'ask_developer', return_value='Сделано в ветке') as developer):
            self.assertTrue(bridge.handle_global_navigation('qa', 'owner', '✅ Берём ' + ident))
            bridge.handle_global_navigation('qa', 'owner', '✅ Берём ' + ident)
        developer.assert_called_once()
        self.assertIn('handoff/' + ident, developer.call_args.args[0])
        verify.assert_called_once()
        self.assertEqual('done', qa_ideas.read()['ideas'][ident]['status'])
        self.assertIn('По этой идее решение уже принято.', self.texts())

    def test_decline_button(self):
        bridge.send_owner_digest('qa', 'owner', now=NOW)
        ident = qa_ideas.idea_id('Подсказывать счёт после статуса')
        bridge.handle_global_navigation('qa', 'owner', '🚫 Не надо ' + ident)
        self.assertEqual('declined', qa_ideas.read()['ideas'][ident]['status'])
        self.assertIn('Больше не предлагается', self.texts()[-1])


if __name__ == '__main__':
    unittest.main()
