import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import bridge


class AssistantThreadTest(unittest.TestCase):
    """06.11: one weeks-long assistant thread — slow, stale deal context, new rules unseen."""

    def setUp(self):
        folder = Path(tempfile.mkdtemp())
        self.calls = []
        for patcher in (patch.object(bridge, 'SESSION_FILE', str(folder / 'session_id.txt')),
                        patch.object(bridge, 'SESSION_META_FILE', str(folder / 'session_thread_state.json')),
                        patch.object(bridge, 'MODEL_FAILURES_FILE', str(folder / 'model_failures.json')),
                        patch.object(bridge, '_run_codex', side_effect=lambda sid, prompt: (self.calls.append(sid), Mock())[1]),
                        patch.object(bridge.model_recovery, 'failure_kind', return_value=None),
                        patch.object(bridge, '_parse_codex_output', side_effect=lambda r: ('ответ', 'T-new'))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_old_thread_without_current_rules_is_not_resumed(self):
        Path(bridge.SESSION_FILE).write_text('T-weeks-old')
        bridge.ask_claude('', 'вопрос')
        self.assertEqual([''], self.calls, 'новый диалог получает актуальные правила')
        bridge.ask_claude('', 'ещё вопрос')
        self.assertEqual(['', 'T-new'], self.calls, 'в тот же день диалог продолжается')

    def test_changed_rules_start_a_new_thread(self):
        bridge.ask_claude('', 'вопрос')
        with patch.object(bridge, 'SYSTEM_PROMPT', bridge.SYSTEM_PROMPT + ' новое правило'):
            bridge.ask_claude('', 'вопрос')
        self.assertEqual(['', ''], self.calls)

    def test_rules_tell_the_assistant_it_cannot_write(self):
        self.assertIn('не пиши «соединение недоступно»', bridge.SYSTEM_PROMPT)
        self.assertIn('Измени в сделке N предмет договора', bridge.SYSTEM_PROMPT)


if __name__ == '__main__':
    unittest.main()
